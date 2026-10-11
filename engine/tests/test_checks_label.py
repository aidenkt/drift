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


def test_buried_constant_sees_its_formula_neighbours_and_path():
    c = constant("Fleet_Model!B11", 1.2, embedded=True, formula="=B6*Inputs!$B$17*1.2/1000000")
    c["outputs"] = ["Fleet_Model!D16"]
    clues = label.describe(c, Workbook(), Graph())
    assert clues["row_label"] == "Collision and damage ($M)"
    assert clues["col_header"] == "EV"
    assert clues["combined_with"] == ["Rental days", "ICE collision and damage cost per rental day"]
    assert clues["paths_to_outputs"] == [
        "Collision and damage ($M) → Segment contribution ($M) → Adjusted Corporate EBITDA ($M)"]


def test_literal_copied_across_a_row_uses_its_first_cell():
    c = constant("Fleet_Model!B11:C11", 1.2, embedded=True, formula="=B6*Inputs!$B$17*1.2/1000000")
    c["cells"] = ["Fleet_Model!B11", "Fleet_Model!C11"]
    clues = label.describe(c, Workbook(), Graph())
    assert clues["row_label"] == "Collision and damage ($M)"


def test_input_cell_sees_unit_and_note():
    clues = label.describe(constant("Inputs!B11", 0.72), Workbook(), Graph())
    assert clues["row_label"] == "EV residual value at disposal"
    assert clues["row_text_right"][0] == "% of cost"
    assert clues["row_text_right"][1].startswith("KEY ASSUMPTION")


def test_market_answer_sets_driver(monkeypatch):
    llm_returns(monkeypatch, {
        "label": "Residual value of an EV at disposal (% of cost)", "role": "market", "unit": "% of cost",
        "search": ["used EV prices 2023", "used Tesla Model 3 value decline"],
        "events": ["Tesla price cuts 2023"],
    })
    c = constant("Inputs!B11", 0.72)
    label.apply(c, Workbook(), Graph())
    assert c["driver"] == "residual_value_of_an_ev_at_disposal_of_cost"
    assert c["label_source"] == "llm"
    assert c["confirmed"] is False
    assert c["search"] == ["used EV prices 2023", "used Tesla Model 3 value decline"]
    assert c["events"] == ["Tesla price cuts 2023"]
    assert "graph_summary" in c


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


def test_apply_all_labels_in_one_call(monkeypatch):
    calls = []

    def fake(system, user, schema, name):
        calls.append(name)
        n = user.count('"index"')
        return {"items": [{"index": i, "label": f"thing {i}", "role": "internal", "unit": "", "search": []} for i in range(n)]}

    monkeypatch.setattr(label, "chat_json", fake)
    consts = [constant("Inputs!B8", 61), constant("Inputs!B11", 0.72), constant("Inputs!B17", 3.4),
              constant("Fleet_Model!B6", 365, embedded=True, formula="=B5*365*Inputs!$B$7")]
    label.apply_all(consts, Workbook(), Graph())
    assert calls == ["labels"]  # one batch call; 365 handled by the rule
    assert [c["label_source"] for c in consts] == ["llm", "llm", "llm", "header"]
    assert consts[3]["role"] == "unit"


def test_margin_over_a_benchmark_is_a_contract_term(monkeypatch):
    # the real run: the LLM called the loan margin "market" and it was then checked against SOFR pages
    llm_returns(monkeypatch, {"label": "Term loan margin over SOFR (%)", "role": "market", "unit": "%",
                              "search": ["Term loan margin over SOFR 2026"], "events": ["leveraged loan spreads 2026"]})
    c = constant("Inputs!B17", 0.0275)
    label.apply(c, Workbook(), Graph())
    assert c["role"] == "internal"
    assert c["driver"] is None and c["search"] == [] and c["events"] == []


def test_the_benchmark_itself_stays_market(monkeypatch):
    llm_returns(monkeypatch, {"label": "SOFR reference rate (% per year)", "role": "market", "unit": "%",
                              "search": ["SOFR rate 2026"], "events": ["Fed decision 2026"]})
    c = constant("Inputs!B17", 0.0366)
    label.apply(c, Workbook(), Graph())
    assert c["role"] == "market" and c["driver"] == "sofr_reference_rate_per_year"


def test_prompt_names_what_is_not_market():
    for words in ("loan margin", "beta", "equity risk premium", "terminal growth", "SOFR", "tariff"):
        assert words in label.SYSTEM
