import json
from pathlib import Path

import jsonschema
import pytest

from checks import assess, news, scrape
from checks.openai_client import LLMUnavailable

SCHEMA = json.loads((Path(__file__).parents[2] / "schema" / "constant.schema.json").read_text())
CHECK_SCHEMA = SCHEMA["$defs"]["constant"]["properties"]["check"]

PAGE = {"id": 1, "url": "https://example.com/ev", "publisher": "example.com", "date": "2023-07-12",
        "title": "", "text": "Used EV prices fell 29.5% in June compared with a year earlier."}
EV = {"cell": "Inputs!B11", "value": 0.72, "label": "Residual value of an EV at disposal (% of cost)",
      "driver": "ev_residual", "search": ["used EV prices 2023"]}


@pytest.fixture(autouse=True)
def clear_cache():
    news._pages.clear()


def test_ev_residual_comes_back_stale(monkeypatch):
    monkeypatch.setattr(scrape, "gather", lambda *a: [PAGE])
    monkeypatch.setattr(assess, "chat_json", lambda *a: {
        "p_stale": 0.95, "kind": "change", "number": -29.5, "transform": None, "then": None, "now": None,
        "quotes": ["Used EV prices fell 29.5% in June compared with a year earlier."], "page": 1,
    })
    c = news.check(EV, "2022-12-15", "2023-12-04")
    jsonschema.validate(c, CHECK_SCHEMA)
    assert c["status"] == "stale"
    assert c["live"] == pytest.approx(0.72 * 0.705)
    assert c["as_of"] == "2023-12-04"


def test_llm_down_is_unknown(monkeypatch):
    monkeypatch.setattr(scrape, "gather", lambda *a: [PAGE])

    def down(*a):
        raise LLMUnavailable("no key")

    monkeypatch.setattr(assess, "chat_json", down)
    c = news.check(EV, "2022-12-15", "2023-12-04")
    assert c["status"] == "unknown"
    jsonschema.validate(c, CHECK_SCHEMA)


def test_crash_is_unknown(monkeypatch):
    def boom(*a):
        raise RuntimeError("bright data exploded")

    monkeypatch.setattr(scrape, "gather", boom)
    assert news.check(EV, "2022-12-15", "2023-12-04")["status"] == "unknown"


def test_cells_sharing_a_driver_scrape_once(monkeypatch):
    calls = []
    monkeypatch.setattr(scrape, "gather", lambda *a: calls.append(a) or [])
    news.check({**EV, "cell": "Fleet_Model!B13"}, "2022-12-15", "2023-12-04")
    news.check({**EV, "cell": "Fleet_Model!C13"}, "2022-12-15", "2023-12-04")
    assert len(calls) == 1


def test_as_of_defaults_to_env(monkeypatch):
    monkeypatch.setattr(scrape, "gather", lambda *a: [])
    monkeypatch.setenv("DRIFT_AS_OF", "2023-12-04")
    assert news.check(EV, "2022-12-15")["as_of"] == "2023-12-04"


def test_scrape_is_told_the_value(monkeypatch):
    calls = []
    monkeypatch.setattr(scrape, "gather", lambda *a: calls.append(a) or [])
    news.check(EV, "2022-12-15", "2023-12-04")
    assert calls[0][-1] == 0.72  # scrape.gather skips the figure searches when FRED already gives this value


def test_threads_sharing_a_driver_scrape_once_and_others_do_not_wait(monkeypatch):
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    active, peak, calls = [0], [0], []
    lock = threading.Lock()

    def slow_gather(label, *a):
        with lock:
            calls.append(label)
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.05)
        with lock:
            active[0] -= 1
        return []

    monkeypatch.setattr(scrape, "gather", slow_gather)
    constants = [{**EV, "cell": f"S!A{i}", "driver": f"driver_{i % 4}", "label": f"label {i % 4}"} for i in range(12)]
    with ThreadPoolExecutor(12) as pool:
        checks = list(pool.map(lambda c: news.check(c, "2022-12-15", "2023-12-04"), constants))
    assert sorted(calls) == ["label 0", "label 1", "label 2", "label 3"]  # once per driver
    assert peak[0] > 1  # different drivers are scraped at the same time
    assert all(c["status"] == "unknown" for c in checks)
