import json
from pathlib import Path

import jsonschema
import pytest

from checks.verify import build_check, effects_from_sensitivity, numbers_in, suggested_value

SCHEMA = json.loads((Path(__file__).parents[2] / "schema" / "constant.schema.json").read_text())
CHECK_SCHEMA = SCHEMA["$defs"]["constant"]["properties"]["check"]

AXIOS = {
    "id": 1, "url": "https://www.axios.com/2024/01/11/hertz-evs", "publisher": "axios.com", "date": "2024-01-11",
    "text": "A CCC report found collision repair on EVs cost about 56% more than on gas cars in 2022.\nOther text.",
}
HERTZ = {
    "id": 2, "url": "https://www.sec.gov/hertz-q4", "publisher": "sec.gov", "date": "2024-02-06",
    "text": "Fleet interest was $91 per unit per month in Q4 2023, compared with $55 in Q4 2022.",
}
PAGES = [AXIOS, HERTZ]


def finding(**kw):
    base = {"p_stale": 0.9, "kind": "none", "number": None, "transform": None, "then": None, "now": None, "quotes": [], "page": None}
    return {**base, **kw}


def run(value, f):
    check = build_check({"cell": "X!A1", "value": value}, f, PAGES, "2023-12-04")
    jsonschema.validate(check, CHECK_SCHEMA)
    return check


def test_real_quote_gives_suggestion():
    c = run(1.2, finding(kind="level", number=56, transform="percent_more_to_ratio",
                         quotes=["collision repair on EVs cost about 56% more than on gas cars"], page=1))
    assert c["live"] == pytest.approx(1.56)
    assert c["drift_pct"] == 30.0
    assert c["status"] == "stale"
    assert c["source_url"] == AXIOS["url"]
    assert c["evidence"][0]["quote"].startswith("collision repair")


def test_made_up_quote_is_dropped():
    c = run(1.2, finding(kind="level", number=60, transform="percent_more_to_ratio",
                         quotes=["EV repairs cost 60% more than gas cars"], page=1))
    assert c["live"] is None
    assert c["evidence"] == []
    assert c["status"] == "stale"  # p_stale 0.9 alone still flags it


def test_number_not_in_quote_is_dropped():
    c = run(1.2, finding(kind="level", number=48, transform="percent_more_to_ratio",
                         quotes=["collision repair on EVs cost about 56% more than on gas cars"], page=1))
    assert c["live"] is None
    assert len(c["evidence"]) == 1  # the quote is real, so it still shows


def test_quote_from_a_different_page_is_dropped():
    c = run(1.2, finding(kind="level", number=56, transform="percent_more_to_ratio",
                         quotes=["collision repair on EVs cost about 56% more than on gas cars"], page=2))
    assert c["live"] is None


def test_ratio_of_levels_fleet_debt_cost():
    c = run(0.034, finding(kind="ratio_of_levels", then=55, now=91,
                           quotes=["Fleet interest was $91 per unit per month in Q4 2023, compared with $55 in Q4 2022."], page=2))
    assert c["live"] == pytest.approx(0.034 * 91 / 55)
    assert c["status"] == "stale"


def test_fresh_control_stays_current():
    page = {"id": 1, "url": "https://example.com/fees", "text": "Buyer fees stay at 1.5% of the sale price."}
    c = build_check({"cell": "Fleet_Model!B13", "value": 0.015},
                    finding(p_stale=0.2, kind="level", number=1.5, transform="percent_to_decimal",
                            quotes=["Buyer fees stay at 1.5% of the sale price."], page=1),
                    [page], "2023-12-04")
    assert c["live"] == pytest.approx(0.015)
    assert c["status"] == "current"


def test_wrong_units_are_dropped():
    page = {"id": 1, "url": "https://example.com", "text": "The rate was 5.63% at year end."}
    c = build_check({"cell": "Inputs!B16", "value": 0.034},
                    finding(p_stale=0.5, kind="level", number=5.63, transform="as_is",
                            quotes=["The rate was 5.63% at year end."], page=1),
                    [page], "2023-12-04")
    assert c["live"] is None
    assert c["status"] == "unknown"


def test_no_pages_is_unknown():
    c = build_check({"cell": "X!A1", "value": 1.0}, finding(p_stale=0.5), [], "2023-12-04")
    assert c["status"] == "unknown"
    jsonschema.validate(c, CHECK_SCHEMA)


@pytest.mark.parametrize("f, expected", [
    ({"kind": "change", "number": -30.6}, 0.72 * 0.694),
    ({"kind": "level", "number": 5.63, "transform": "percent_to_decimal"}, 0.0563),
    ({"kind": "level", "number": 30, "transform": "percent_less_to_ratio"}, 0.70),
    ({"kind": "ratio_of_levels", "then": 100, "now": 69.4}, 0.72 * 0.694),
    ({"kind": "none"}, None),
])
def test_suggested_value(f, expected):
    got = suggested_value(0.72, f)
    assert got == (pytest.approx(expected) if expected is not None else None)


def test_numbers_in_handles_money_and_commas():
    assert numbers_in("$4.2B for 100,000 Teslas, down 29.5%") == [4.2, 100000.0, 29.5]


def test_events_need_a_real_quote():
    f = finding(events=[
        {"summary": "CCC report", "direction": "raises", "page": 1,
         "quote": "collision repair on EVs cost about 56% more than on gas cars"},
        {"summary": "made up", "direction": "raises", "page": 1, "quote": "Repair costs doubled overnight."},
    ])
    c = run(1.2, f)
    assert [e["summary"] for e in c["events"]] == ["CCC report"]
    assert c["events"][0]["url"] == AXIOS["url"]


def test_sentences_with_unsourced_numbers_are_dropped():
    f = finding(kind="level", number=56, transform="percent_more_to_ratio",
                quotes=["collision repair on EVs cost about 56% more than on gas cars"], page=1,
                assumption="EV repair cost uplift should be 1.56x, not 1.2x, per CCC.",
                prediction="EBITDA falls by about $21M.",
                next_steps=["Update X!A1 to 1.56", "Cut the estimate by 40%", "Rerun the model"])
    c = run(1.2, f)
    assert c["assumption"].startswith("EV repair cost uplift should be 1.56x")
    assert c["prediction"] is None  # $21M appears in no source
    assert c["next_steps"] == ["Update X!A1 to 1.56", "Rerun the model"]


def test_zero_value_tariff_goes_stale():
    page = {"id": 1, "url": "https://cbp.gov/x", "text": "A 50% duty on Canada-origin furniture is in force from August 22."}
    c = build_check({"cell": "Assumptions!B23", "value": 0.0},
                    finding(kind="level", number=50, transform="percent_to_decimal",
                            quotes=["A 50% duty on Canada-origin furniture is in force from August 22."], page=1),
                    [page], "2026-10-10")
    assert c["live"] == pytest.approx(0.5)
    assert c["drift_pct"] is None
    assert c["status"] == "stale"
    jsonschema.validate(c, CHECK_SCHEMA)


SENS = {  # graph's impact.sensitivity: +1% on the constant
    "bump": {"from": 1.2, "to": 1.212, "kind": "relative", "size": 0.01},
    "effects": [
        {"output": "M!B9", "label": "EBITDA", "baseline": 106.0, "delta": -0.5, "pct": -0.471698, "direction": "falls",
         "path": [{"cell": "M!B5", "label": "Repair cost", "col_header": None, "formula": "=B4*X!A1",
                   "baseline": 40.0, "delta": 0.4, "pct": 1.0, "direction": "rises"}]},
        {"output": "M!B12", "label": "Enterprise value (NPV)", "baseline": 905.5, "delta": -6.0, "pct": -0.662617,
         "direction": "falls", "path": []},
        {"output": "M!B14", "label": "Share count", "baseline": 50.0, "delta": 0.0, "pct": 0.0,
         "direction": "unchanged", "path": []},
    ],
}


def test_effects_come_from_the_recalculated_model():
    f = finding(kind="level", number=56, transform="percent_more_to_ratio",
                quotes=["collision repair on EVs cost about 56% more than on gas cars"], page=1,
                effects=[{"output": "EBITDA", "direction": "up"}])  # anything the model says is ignored
    c = build_check({"cell": "X!A1", "value": 1.2, "sensitivity": SENS}, f, PAGES, "2023-12-04")
    assert c["effects"] == [{"output": "EBITDA", "direction": "down"},
                            {"output": "Enterprise value (NPV)", "direction": "down"},
                            {"output": "Share count", "direction": "unclear"}]
    jsonschema.validate(c, CHECK_SCHEMA)


def test_effects_flip_when_the_constant_should_fall():
    assert effects_from_sensitivity(SENS, 1.2, 1.0)[:2] == [{"output": "EBITDA", "direction": "up"},
                                                           {"output": "Enterprise value (NPV)", "direction": "up"}]


def test_no_effects_without_a_live_value_or_when_the_model_cant_recalculate():
    assert build_check({"cell": "X!A1", "value": 1.2, "sensitivity": SENS}, finding(), PAGES, "2023-12-04")["effects"] == []
    flat = {"bump": None, "effects": [{"output": "M!B9", "label": "EBITDA", "baseline": None, "delta": None,
                                       "pct": None, "direction": None, "path": []}]}
    f = finding(kind="level", number=56, transform="percent_more_to_ratio",
                quotes=["collision repair on EVs cost about 56% more than on gas cars"], page=1,
                prediction="EBITDA falls by 0.5.")
    c = build_check({"cell": "X!A1", "value": 1.2, "sensitivity": flat}, f, PAGES, "2023-12-04")
    assert c["effects"] == [{"output": "EBITDA", "direction": "unclear"}]
    assert c["prediction"] is None  # no recalculated numbers to back 0.5
    jsonschema.validate(c, CHECK_SCHEMA)


def test_sensitivity_figures_and_scaled_impact_are_allowed():
    # live 1.56 is +0.36, thirty times the +0.012 bump, so EBITDA moves about -15 and EV about -180
    f = finding(kind="level", number=56, transform="percent_more_to_ratio",
                quotes=["collision repair on EVs cost about 56% more than on gas cars"], page=1,
                prediction="A 1% rise lowers EBITDA by 0.5; at 1.56 EBITDA falls about 15 and EV about 180.")
    c = build_check({"cell": "X!A1", "value": 1.2, "sensitivity": SENS}, f, PAGES, "2023-12-04")
    assert c["prediction"].startswith("A 1% rise lowers EBITDA by 0.5")
