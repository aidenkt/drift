import pytest

from checks import label
from checks.openai_client import LLMUnavailable
from hertz_fake import Graph, Workbook, constant


@pytest.fixture(autouse=True)
def clear_cache():
    label._cache.clear()


def llm_returns(monkeypatch, answer):
    calls = []

    def fake(system, user, schema, name):
        calls.append(user)
        return answer

    monkeypatch.setattr(label, "chat_json", fake)
    return calls


def llm_down(monkeypatch):
    def fake(*a, **kw):
        raise LLMUnavailable("no key")

    monkeypatch.setattr(label, "chat_json", fake)


def test_unit_constants_skip_the_llm(monkeypatch):
    calls = llm_returns(monkeypatch, {})
    c = constant("Fleet_Model!B6", 365, embedded=True, formula="=B5*365*Inputs!$B$7")
    label.apply(c, Workbook(), Graph())
    assert c["role"] == "unit"
    assert c["driver"] is None
    assert calls == []


def test_buried_constant_sees_its_formula_neighbours():
    c = constant("Fleet_Model!B11", 1.2, embedded=True, formula="=B6*Inputs!$B$17*1.2/1000000")
    clues = label.describe(c, Workbook(), Graph())
    assert clues["row_label"] == "Collision and damage ($M)"
    assert clues["col_header"] == "EV"
    assert "ICE collision and damage cost per rental day / Value" in clues["formula_uses"]
    assert any(t.startswith("Rental days") for t in clues["formula_uses"])
    assert any(t.startswith("Segment contribution") for t in clues["feeds_into"])


def test_input_cell_sees_unit_and_note():
    clues = label.describe(constant("Inputs!B11", 0.72), Workbook(), Graph())
    assert clues["row_label"] == "EV residual value at disposal"
    assert clues["row_text_right"][0] == "% of cost"
    assert clues["row_text_right"][1].startswith("KEY ASSUMPTION")


def test_market_answer_sets_driver(monkeypatch):
    llm_returns(monkeypatch, {
        "label": "Residual value of an EV at disposal (% of cost)", "role": "market", "unit": "% of cost",
        "search": ["used EV prices 2023", "used Tesla Model 3 value decline"],
    })
    c = constant("Inputs!B11", 0.72)
    label.apply(c, Workbook(), Graph())
    assert c["driver"] == "residual_value_of_an_ev_at_disposal_of_cost"
    assert c["label_source"] == "llm"
    assert c["confirmed"] is False
    assert c["search"] == ["used EV prices 2023", "used Tesla Model 3 value decline"]


def test_lever_is_labeled_but_not_checked(monkeypatch):
    llm_returns(monkeypatch, {"label": "Rental revenue per day ($)", "role": "lever", "unit": "$ / day",
                              "search": ["rental car revenue per day 2023"]})
    c = constant("Inputs!B8", 61)
    label.apply(c, Workbook(), Graph())
    assert c["role"] == "lever"
    assert c["driver"] is None  # pipeline skips the check when driver is None


def test_llm_down_falls_back_to_row_label(monkeypatch):
    llm_down(monkeypatch)
    c = constant("Inputs!B17", 3.4)
    label.apply(c, Workbook(), Graph())
    assert c["label"] == "ICE collision and damage cost per rental day"
    assert c["role"] == "internal"
    assert c["label_source"] == "header"


def test_bad_llm_answer_falls_back(monkeypatch):
    llm_returns(monkeypatch, {"label": "", "role": "market", "unit": "", "search": []})
    c = constant("Inputs!B17", 3.4)
    label.apply(c, Workbook(), Graph())
    assert c["role"] == "internal"


def test_same_clues_call_the_llm_once(monkeypatch):
    calls = llm_returns(monkeypatch, {"label": "x", "role": "internal", "unit": "", "search": []})
    for _ in range(3):
        label.apply(constant("Inputs!B17", 3.4), Workbook(), Graph())
    assert len(calls) == 1
