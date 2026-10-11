import json

import httpx

from checks import drivers, scrape

SERP = json.dumps({"organic": [
    {"link": "https://www.example.com/used-ev-prices", "title": "Used EV prices fall", "source": "Example News",
     "description": "Used EV prices fell 29.5% in June...", "extensions": [{"type": "text", "text": "Jul 12, 2023"}]},
    {"link": "https://www.example.com/blocked", "title": "Paywalled", "source": "Blocked",
     "description": "Used EV values dropped 31% this year, dealers say."},
]})
ARTICLE = """<html><head><script>var x = 99;</script><style>p{}</style></head><body>
<nav>Home 2023</nav>
<p>Used EV prices fell 29.5% in June compared with a year earlier, according to iSeeCars.</p>
<p>Gas car prices were roughly flat.</p>
<p>Weather today.</p>
</body></html>"""
FRED = json.dumps({"observations": [
    {"date": "2022-12-14", "value": "4.30"}, {"date": "2022-12-15", "value": "."},
    {"date": "2023-12-01", "value": "5.32"}, {"date": "2023-12-04", "value": "5.31"},
]})


def test_html_to_text_drops_scripts_and_nav():
    text = scrape.html_to_text(ARTICLE)
    assert "var x" not in text and "Home 2023" not in text
    assert "Used EV prices fell 29.5% in June" in text


def test_gather_builds_pages(monkeypatch, tmp_path):
    monkeypatch.setattr(scrape, "CACHE", tmp_path)
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_SERP_ZONE", "serp")
    monkeypatch.setenv("BRIGHTDATA_UNLOCKER_ZONE", "unlocker")
    monkeypatch.setenv("FRED_API_KEY", "k")
    fetched = []

    def fake_cached(key, fetch):
        fetched.append(key)
        if key[0] == "fred":
            return FRED
        if "google.com" in key[2]:
            return SERP
        return "" if key[2].endswith("blocked") else ARTICLE

    monkeypatch.setattr(scrape, "_cached", fake_cached)
    pages = scrape.gather("Used EV residual value", ["used EV prices 2023", "SOFR 2023"], "2022-12-15", "2023-12-04")

    fred = pages[0]
    assert fred["url"] == "https://fred.stlouisfed.org/series/SOFR"
    assert "Value on 2022-12-14: 4.3%" in fred["text"]  # holiday "." skipped, last value on or before built_on
    assert "Value on 2023-12-04: 5.31%" in fred["text"]

    article = pages[1]
    assert article["publisher"] == "Example News" and article["date"] == "2023-07-12"
    assert "fell 29.5%" in article["text"]
    assert "Weather" not in article["text"]  # no topic words, no numbers
    blocked = pages[2]
    assert blocked["text"] == "Used EV values dropped 31% this year, dealers say."  # snippet when the page can't be fetched
    assert blocked["date"] is None
    assert [p["id"] for p in pages] == [1, 2, 3]
    assert sum(1 for k in fetched if k[0] == "brightdata" and k[2].endswith("used-ev-prices")) == 1  # fetched once


def test_no_keys_returns_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(scrape, "CACHE", tmp_path)
    for k in ("BRIGHTDATA_API_KEY", "BRIGHTDATA_SERP_ZONE", "BRIGHTDATA_UNLOCKER_ZONE", "FRED_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert scrape.gather("SOFR", ["SOFR"], "2022-12-15", "2023-12-04") == []


def test_cache_skips_second_fetch(monkeypatch, tmp_path):
    monkeypatch.setattr(scrape, "CACHE", tmp_path)
    calls = []

    def fetch():
        calls.append(1)
        return "body"

    assert scrape._cached(("a",), fetch) == "body"
    assert scrape._cached(("a",), fetch) == "body"
    assert len(calls) == 1


def test_search_adds_the_year(monkeypatch, tmp_path):
    monkeypatch.setattr(scrape, "CACHE", tmp_path)
    monkeypatch.setenv("BRIGHTDATA_SERP_ZONE", "serp")
    urls = []
    monkeypatch.setattr(scrape, "_brightdata", lambda zone, url, data_format=None: urls.append(url) or "")
    scrape._search("used EV prices", "2022-12-15", "2023-12-04")
    scrape._search("SOFR 2022", "2022-12-15", "2023-12-04")
    assert "q=used+EV+prices+2023" in urls[0]
    assert "q=SOFR+2022&" in urls[1]


def test_brightdata_empty_body_is_retried_and_not_cached(monkeypatch, tmp_path):
    monkeypatch.setattr(scrape, "CACHE", tmp_path)
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    calls = []

    class Response:
        text = ""
        headers = {"x-brd-error": "captcha"}

        def raise_for_status(self):
            pass

    monkeypatch.setattr(scrape.httpx, "post", lambda *a, **kw: calls.append(1) or Response())
    assert scrape._brightdata("serp", "https://www.google.com/search?q=x") == ""
    assert len(calls) == 2
    assert list(tmp_path.iterdir()) == []


def test_pages_are_fetched_in_parallel(monkeypatch, tmp_path):
    import threading
    import time

    monkeypatch.setattr(scrape, "CACHE", tmp_path)
    monkeypatch.setattr(scrape, "_fred_page", lambda *a: None)
    hits = [{"url": f"https://example.com/{i}", "publisher": "x", "date": None, "title": "", "snippet": "EV prices 5%"}
            for i in range(6)]
    monkeypatch.setattr(scrape, "_search", lambda *a: hits)
    active, peak = [0], [0]
    lock = threading.Lock()

    def slow_fetch(url):
        with lock:
            active[0] += 1
            peak[0] = max(peak[0], active[0])
        time.sleep(0.05)
        with lock:
            active[0] -= 1
        return ""

    monkeypatch.setattr(scrape, "_fetch_text", slow_fetch)
    pages = scrape.gather("EV prices", ["EV prices"], "2026-08-01", "2026-10-10", ["EV tariffs"])
    assert peak[0] > 1
    assert len(pages) == 6  # 3 per query, no URL twice


def test_fred_page_carries_its_observations(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "k")
    monkeypatch.setattr(scrape, "_cached", lambda key, fetch: FRED)
    page = scrape._fred_page("SOFR reference rate", "2022-12-15", "2023-12-04")
    recent = page["fred"].pop("then_recent")
    assert recent[-1] == 4.3 and len(recent) <= scrape.THEN_RECENT  # the prints up to built_on, latest last
    assert page["fred"] == {"series": "SOFR", "unit": "percent", "then": 4.3, "then_date": "2022-12-14",
                            "now": 5.31, "now_date": "2023-12-04"}


def test_series_is_the_constants_quantity_only_when_label_and_value_agree():
    sofr = {"series": "SOFR", "unit": "percent", "then": 3.66, "now": 3.87}
    assert drivers.series_scale("SOFR reference rate (% per year)", 0.0366, sofr) == 0.01
    assert drivers.series_scale("SOFR (%)", 3.66, sofr) == 1  # a model that holds percents as 3.66
    assert drivers.series_scale("Term loan margin over SOFR (%)", 0.0366, sofr) is None  # priced off it
    assert drivers.series_scale("SOFR reference rate", 0.0641, sofr) is None  # SOFR plus a margin in one cell
    assert drivers.series_scale("Fed funds rate", 0.0366, sofr) is None  # another series
    assert drivers.fred_series_for("Brent crude oil price ($/bbl)")[0] == "DCOILBRENTEU"  # not WTI via "crude"
    assert drivers.fred_series_for("20-year Treasury yield, 2026") is None  # "2" and "10" are whole words
    assert drivers.fred_series_for("Eurozone HICP") is None


def _hits(monkeypatch, readable=lambda url: False):
    """Every search returns three hits of its own; a page that can't be read becomes its search snippet."""
    searched = []

    def search(query, built_on, as_of):
        searched.append(query)
        return [{"url": f"https://example.com/{query}/{i}", "publisher": "x", "date": None, "title": "", "snippet": "5%"}
                for i in range(3)]

    monkeypatch.setattr(scrape, "_search", search)
    monkeypatch.setattr(scrape, "_fetch_text", lambda url: "EV prices fell 29.5% in June." if readable(url) else "")
    return searched


def test_fred_covered_constant_searches_only_for_events(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "k")
    monkeypatch.setattr(scrape, "_cached", lambda key, fetch: FRED)
    searched = _hits(monkeypatch)
    args = ("SOFR reference rate (% per year)", ["SOFR rate", "SOFR history"], "2022-12-15", "2023-12-04", ["Fed decision", "CPI", "FOMC"])
    pages = scrape.gather(*args, 0.043)
    assert searched == ["Fed decision", "CPI"]
    assert [p["kind"] for p in pages] == ["data"] + ["event"] * 6
    searched.clear()
    scrape.gather(*args, 0.07)  # not what SOFR printed on built_on: FRED won't supply the value, so look for figures
    assert searched == ["SOFR rate", "SOFR history", "Fed decision", "CPI", "FOMC"]


def test_llm_gets_eight_pages_read_ones_before_snippets(monkeypatch):
    monkeypatch.setattr(scrape, "_fred_page", lambda *a: None)
    _hits(monkeypatch, readable=lambda url: url.endswith(("a/2", "c/1", "f/2")))  # 18 fetched, 3 could be read
    pages = scrape.gather("EV prices", ["a", "b", "c"], "2026-08-01", "2026-10-10", ["d", "e", "f"])
    urls = [p["url"].removeprefix("https://example.com/") for p in pages]
    assert urls == ["a/0", "a/2", "b/0", "c/0", "c/1", "d/0", "e/0", "f/2"]  # the 3 read, then top hits' snippets
    assert [len(p["text"]) > 2 for p in pages] == [False, True, False, False, True, False, False, True]
    assert [p["id"] for p in pages] == list(range(1, 9))


def test_failed_fetch_is_not_tried_again(monkeypatch, tmp_path):
    monkeypatch.setattr(scrape, "CACHE", tmp_path)
    calls = []

    def fetch():
        calls.append(1)
        raise httpx.ReadTimeout("slow")

    assert scrape._cached(("dead",), fetch) == ""
    assert scrape._cached(("dead",), fetch) == ""
    assert len(calls) == 1
    assert list(tmp_path.iterdir()) == []

    def busy():
        calls.append(1)
        raise httpx.HTTPStatusError("429", request=None, response=None)

    assert scrape._cached(("busy",), busy) == scrape._cached(("busy",), busy) == ""
    assert len(calls) == 3  # a rate limit is not a dead URL: tried again next time


def test_page_fetch_is_tried_once_with_a_short_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(scrape, "CACHE", tmp_path)
    monkeypatch.setenv("BRIGHTDATA_API_KEY", "k")
    monkeypatch.setenv("BRIGHTDATA_UNLOCKER_ZONE", "unlocker")
    timeouts = []

    class Empty:
        text = ""
        headers = {"x-brd-error": "blocked"}

        def raise_for_status(self):
            pass

    monkeypatch.setattr(scrape.httpx, "post", lambda *a, **kw: timeouts.append(kw["timeout"]) or Empty())
    assert scrape._fetch_text("https://example.com/slow") == ""
    assert timeouts == [scrape.PAGE_TIMEOUT]
    assert scrape.PAGE_TIMEOUT <= 20


def test_cache_is_written_whole_from_several_threads(monkeypatch, tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(scrape, "CACHE", tmp_path)
    body = "x" * 200_000
    with ThreadPoolExecutor(8) as pool:
        got = list(pool.map(lambda i: scrape._cached(("same",), lambda: body), range(32)))
    assert set(got) == {body}
    assert [f.suffix for f in tmp_path.iterdir()] == [".txt"]  # no half-written leftovers
