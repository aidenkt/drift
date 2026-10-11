import json
from pathlib import Path

import jsonschema
import pytest

from checks.verify import build_check, effects_from_sensitivity, numbers_in, quote_in_text, suggested_value

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
    assert c["status"] == "unknown"  # p_stale 0.9 with no verified quote behind it flags nothing


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


def _fx_page(text):
    return [{"id": 1, "url": "https://fred.stlouisfed.org/series/X", "text": text}]


def test_two_percent_fx_move_is_stale():
    text = "Value on 2026-10-02: 1.1259."
    c = build_check({"cell": "Assumptions!B21", "value": 1.1519, "label": "EUR/USD ($ per EUR)"},
                    finding(kind="level", number=1.1259, transform="as_is", quotes=[text], page=1),
                    _fx_page(text), "2026-10-10")
    assert c["drift_pct"] == -2.3
    assert c["status"] == "stale"


def test_rate_is_judged_in_points():
    text = "Value on 2026-10-08: 3.87%."
    c = build_check({"cell": "P&L!C35:G35", "value": 0.0366, "label": "Term loan base rate (SOFR, annual %)"},
                    finding(kind="level", number=3.87, transform="percent_to_decimal", quotes=[text], page=1),
                    _fx_page(text), "2026-10-10")
    assert c["status"] == "stale"  # +0.21pp


def test_rounded_estimate_from_the_sensitivity_survives():
    text = "Value on 2026-10-02: 1.1259."
    sens = {"bump": {"from": 1.1519, "to": 1.163419, "kind": "relative", "size": 0.01},
            "effects": [{"output": "P&L!C27", "label": "EBITDA", "baseline": 105.98, "delta": -0.852,
                         "pct": -0.8, "direction": "falls", "path": []}]}
    c = build_check({"cell": "Assumptions!B21", "value": 1.1519, "label": "EUR/USD", "sensitivity": sens},
                    finding(kind="level", number=1.1259, transform="as_is", quotes=[text], page=1,
                            prediction="A weaker euro raises EBITDA by about 2.0."),  # exact is 1.92
                    _fx_page(text), "2026-10-10")
    assert c["prediction"] == "A weaker euro raises EBITDA by about 2.0."


def test_dropped_suggestion_logs_why(caplog):
    caplog.set_level("INFO", logger="checks.verify")
    run(1.2, finding(kind="level", number=60, transform="percent_more_to_ratio",
                     quotes=["EV repairs cost 60% more than gas cars"], page=1))
    assert "quote not on page 1" in caplog.text


# --- cases from the real run on the August 2026 case study -------------------------------------------------


def _fred(series, name, unit, then, now, then_date="2026-07-31", now_date="2026-10-08"):
    """A FRED data page as scrape._fred_page builds it."""
    pct = "%" if unit == "percent" else ""
    text = (f"FRED series {series} ({name}). Value on {then_date}: {then:g}{pct}. Value on {now_date}: {now:g}{pct}. "
            f"Change between those dates: {(now - then) / then * 100:+.1f}%.")
    return {"id": 1, "kind": "data", "url": f"https://fred.stlouisfed.org/series/{series}", "date": now_date,
            "publisher": "FRED, Federal Reserve Bank of St. Louis", "title": f"FRED {series}", "text": text,
            "fred": {"series": series, "unit": unit, "then": then, "then_date": then_date, "now": now, "now_date": now_date}}


DGS10 = _fred("DGS10", "10-year Treasury yield", "percent", 4.75, 5.22)
DEXUSEU = _fred("DEXUSEU", "US dollars to one euro", "level", 1.1519, 1.1259, now_date="2026-10-02")
SOFR = _fred("SOFR", "Secured Overnight Financing Rate", "percent", 3.66, 3.87)
TREASURY = {"cell": "DCF!B6", "value": 0.0475, "label": "Risk-free rate (10-year US Treasury, %)"}
EURUSD = {"cell": "Assumptions!B21", "value": 1.1519, "label": "EUR/USD exchange rate, 31-Jul-2026 ($ per \u20ac)"}


def _plain(page):
    """The same page from a publisher that is not FRED, so the number has to come through the finding."""
    return {k: v for k, v in page.items() if k != "fred"}


def test_fred_value_is_taken_in_code_whatever_the_llm_reports():
    for f in (finding(kind="level", number=0.0522, transform="as_is", quotes=[DGS10["text"]], page=1),  # the real run
              finding(kind="level", number=9.99, transform="percent_to_decimal", quotes=["made up 9.99%"], page=1),
              finding()):
        c = build_check(TREASURY, f, [DGS10], "2026-10-10")
        assert c["live"] == 0.0522
        assert c["status"] == "stale"  # +0.47pp
        assert c["source_url"] == DGS10["url"]
        assert c["evidence"][0] == {"quote": DGS10["text"], "url": DGS10["url"], "publisher": DGS10["publisher"],
                                    "date": "2026-10-08"}
        jsonschema.validate(c, CHECK_SCHEMA)


def test_fred_level_series_is_used_as_is():
    c = build_check(EURUSD, finding(kind="change", number=-0.023, quotes=[DEXUSEU["text"]], page=1), [DEXUSEU], "2026-10-10")
    assert c["live"] == 1.1259
    assert c["drift_pct"] == -2.3
    assert c["status"] == "stale"
    assert len(c["evidence"]) == 1  # the LLM quoted the FRED page too: shown once
    part = finding(kind="level", number=1.1259, transform="as_is", quotes=["Value on 2026-10-02: 1.1259."], page=1)
    assert len(build_check(EURUSD, part, [DEXUSEU], "2026-10-10")["evidence"]) == 1


def test_fred_is_not_used_for_something_priced_off_the_series():
    margin = {"cell": "Assumptions!B29", "value": 0.0275, "label": "Term loan margin over SOFR (%)"}
    all_in = {"cell": "P&L!C35", "value": 0.0641, "label": "Term loan interest rate (SOFR, %)"}  # SOFR + margin in one cell
    for constant in (margin, all_in):
        c = build_check(constant, finding(p_stale=1.0), [SOFR], "2026-10-10")
        assert c["live"] is None
        assert c["status"] == "unknown"  # the real run called the margin stale on p_stale 1.0 alone
    buried = {"cell": "P&L!C35:G35", "value": 0.0366, "label": "SOFR reference rate (% per year)",
              "formula": "=0.0366+'Assumptions'!$B$29"}  # the literal is SOFR itself
    assert build_check(buried, finding(), [SOFR], "2026-10-10")["live"] == 0.0387


def test_fred_is_not_used_for_another_series_or_one_that_has_not_printed():
    brent = {"cell": "Assumptions!B20", "value": 96.95, "label": "Brent crude oil price for FY2026E ($/bbl)"}
    wti = _fred("DCOILWTICO", "WTI crude oil, $/bbl", "level", 96.5, 96.24)  # near Brent's value, still not Brent
    assert build_check(brent, finding(), [wti], "2026-10-10")["live"] is None
    same_day = _fred("DGS10", "10-year Treasury yield", "percent", 4.75, 4.75, now_date="2026-07-31")
    assert build_check(TREASURY, finding(), [same_day], "2026-08-02")["live"] is None


def test_number_reported_in_the_other_units_is_read_as_written():
    page = _plain(DGS10)
    c = build_check(TREASURY, finding(kind="level", number=0.0522, transform="as_is", quotes=[page["text"]], page=1),
                    [page], "2026-10-10")
    assert c["live"] == 0.0522  # 5.22 as written, in the model's units
    tax = {"id": 1, "url": "https://taxsummaries.pwc.com/x", "title": "",
           "text": "The United States taxes resident corporations at a flat rate of 21%."}
    c = build_check({"cell": "Assumptions!B24", "value": 0.21, "label": "US federal corporate income tax rate (%)"},
                    finding(p_stale=0.05, kind="level", number=0.21, transform="as_is", quotes=[tax["text"]], page=1),
                    [tax], "2026-10-10")
    assert c["live"] == 0.21
    assert c["status"] == "current"


def test_number_absent_in_either_units_is_still_dropped():
    c = run(1.2, finding(kind="level", number=0.48, transform="as_is",
                         quotes=["collision repair on EVs cost about 56% more than on gas cars"], page=1))
    assert c["live"] is None
    page = {"id": 1, "url": "https://example.com", "title": "", "text": "Of 21 states surveyed, most kept their rate."}
    c = build_check({"cell": "A!B24", "value": 0.21}, finding(kind="level", number=0.21, transform="as_is",
                                                             quotes=[page["text"]], page=1), [page], "2026-10-10")
    assert c["live"] is None  # 21 is on the page, but not as a percent


def test_change_reported_as_a_fraction_uses_the_quoted_levels():
    page = _plain(DEXUSEU)
    c = build_check(EURUSD, finding(kind="change", number=-0.023, quotes=[page["text"]], page=1), [page], "2026-10-10")
    assert c["live"] == pytest.approx(1.1259)  # the now-level, not 1.1519 * (1 - 0.023 / 100)
    assert c["status"] == "stale"


def test_change_reported_as_a_fraction_without_levels_is_applied_as_a_percent():
    quote = "Used EV prices fell 29.5% in June compared with a year earlier."
    assert suggested_value(0.72, {"kind": "change", "number": -0.295}, [quote]) == pytest.approx(0.72 * 0.705)
    assert suggested_value(0.72, {"kind": "change", "number": -29.5}, [quote]) == pytest.approx(0.72 * 0.705)


FURNITURE_TODAY = {
    "id": 7, "url": "https://www.furnituretoday.com/tariffs/x", "publisher": "Furniture Today", "date": "2026-08-24",
    "title": "U.S.-Canada trade war ramps up as 50% tariffs take effect",
    "text": "U.S.-Canada trade war ramps up as 50% tariffs take effect - Furniture Today\n"
            "U.S.-Canada trade war ramps up as 50% tariffs take effect\n"
            "The United States imposed 50% tariffs on approximately $20 billion of Canadian goods Saturday after a "
            "three-day extension failed to produce a deal. Canadian Prime Minister Mark Carney responded by announcing "
            "that Canada would match the duties \u201cdollar for dollar,\u201d with retaliatory tariffs taking effect Sept. 8.\n"
            "The U.S. tariffs cover more than 500 product categories, including furniture, lumber and plywood.\n"
            "New 50% tariff on Canadian imports includes furniture",
}
CANADA = {"cell": "Assumptions!B23", "value": 0.0, "label": "Tariff rate on Canada-origin furniture (% of value)"}


def test_quote_made_of_a_title_and_joined_passages_is_found():
    quote = ("U.S.-Canada trade war ramps up as 50% tariffs take effect - Furniture Today\n"
             "U.S.-Canada trade war ramps up as 50% tariffs take effect\n"
             "The United States imposed 50% tariffs on approximately $20 billion of Canadian goods Saturday after a "
             "three-day extension failed to produce a deal. ... The U.S. tariffs cover more than 500 product categories, "
             "including furniture, lumber and plywood.\nNew 50% tariff on Canadian imports includes furniture")
    c = build_check(CANADA, finding(kind="level", number=50, transform="percent_to_decimal", quotes=[quote], page=7),
                    [FURNITURE_TODAY], "2026-10-10")
    assert c["live"] == pytest.approx(0.5)
    assert c["status"] == "stale"
    assert c["source_name"] == "Furniture Today"


def test_quote_matching_is_exact_about_words_and_numbers():
    text = "Rates held at 12.5%.[1] Furniture pays the 12.5% Section 301 duty instead.[2]\nCheck your line \u2013 it\u2019s free."
    assert quote_in_text("Rates held at 12.5%. Furniture pays the 12.5% Section 301 duty instead.", text)  # footnote marks
    assert quote_in_text("Check your line - it's free.", text)  # typographic dash and apostrophe
    assert quote_in_text("Rates held at  12.5%.\n Check your line", text)  # two pieces, both there
    assert not quote_in_text("Rates held at 12.5%.\nFurniture pays a 25% Section 301 duty instead.", text)  # one piece is not
    assert not quote_in_text("Rates held at 12.5%. ... 25%", text)  # a short piece with a number must be there too
    assert not quote_in_text("Rates held ... at 12.5%", text)  # no piece long enough to mean anything
    page = {"id": 1, "url": "https://example.com", "title": "Canada tariffs rise to 50% on furniture", "text": "Snippet."}
    c = build_check(CANADA, finding(kind="level", number=50, transform="percent_to_decimal",
                                    quotes=["Canada tariffs rise to 50% on furniture"], page=1), [page], "2026-10-10")
    assert c["live"] == pytest.approx(0.5)  # the title is part of the page the LLM is shown


VIETNAM = {"cell": "Assumptions!B22", "value": 0.125, "label": "Tariff rate on Vietnam-origin furniture (% of value)"}
AIRLIFT = {"id": 3, "url": "https://airliftusa.com/tariff-updates/vietnam", "title": "US Tariffs on Vietnam 2026",
           "text": "As of September 25, 2026, most Vietnamese goods pay the normal duty for their HTS line plus a 12.5% "
                   "Section 301 duty in force since July 24, 2026.[1] Section 232 goods pay their own rates.[2]"}
WILEY = {"id": 8, "url": "https://www.wiley.law/alert", "title": "",
         "text": "A 12.5% duty (which stacks on existing standard duty rates) for all other investigated trading partners."}


def test_unchanged_control_is_not_stale_whatever_p_stale_says():
    quote = ("As of September 25, 2026, most Vietnamese goods pay the normal duty for their HTS line plus a 12.5% "
             "Section 301 duty in force since July 24, 2026. Section 232 goods pay their own rates.[2]")  # "[1]" dropped
    f = finding(p_stale=1.0, kind="level", number=12.5, transform="percent_to_decimal", quotes=[quote], page=3)
    c = build_check(VIETNAM, f, [AIRLIFT, WILEY], "2026-10-10")
    assert c["live"] == pytest.approx(0.125)
    assert c["status"] == "current"
    # the quote is not on the page and an event "raises": the LLM's own figure is still the model's value
    f = finding(p_stale=1.0, kind="level", number=12.5, transform="percent_to_decimal", quotes=["Vietnam pays 12.5% now."],
                page=3, events=[{"summary": "duty", "direction": "raises", "page": 8, "quote": WILEY["text"]}])
    c = build_check(VIETNAM, f, [AIRLIFT, WILEY], "2026-10-10")
    assert c["live"] is None
    assert len(c["events"]) == 1
    assert c["status"] == "unknown"


def test_stale_without_a_number_needs_a_verified_quote():
    event = {"summary": "CCC report", "direction": "raises", "page": 1,
             "quote": "collision repair on EVs cost about 56% more than on gas cars"}
    assert run(1.2, finding(p_stale=1.0))["status"] == "unknown"  # confidence alone (the real run's beta)
    assert run(1.2, finding(p_stale=1.0, events=[{**event, "quote": "Repair costs doubled."}]))["status"] == "unknown"
    assert run(1.2, finding(p_stale=1.0, events=[{**event, "direction": "unclear"}]))["status"] == "unknown"
    assert run(1.2, finding(p_stale=1.0, events=[event]))["status"] == "stale"
    assert run(1.2, finding(p_stale=0.1))["status"] == "unknown"  # "current" needs a quote as well
    assert run(1.2, finding(p_stale=0.1, events=[{**event, "direction": "unclear"}]))["status"] == "current"


def test_a_quote_that_is_not_on_the_page_is_left_out_and_the_rest_still_count():
    f = finding(kind="level", number=56, transform="percent_more_to_ratio", page=1,
                quotes=["collision repair on EVs cost about 56% more than on gas cars", "Insurers agree: 56% more."])
    c = run(1.2, f)
    assert c["live"] == pytest.approx(1.56)
    assert [e["quote"] for e in c["evidence"]] == ["collision repair on EVs cost about 56% more than on gas cars"]
    f["quotes"] = ["A CCC report found collision repair on EVs", "Insurers agree: 56% more."]  # the number is in the bad one
    assert run(1.2, f)["live"] is None


def test_curly_quotes_the_llm_wrote_as_control_characters_are_put_back():
    quote = "Canada would match the duties \x1cdollar for dollar,\x1d with retaliatory tariffs taking effect Sept. 8."
    f = finding(kind="level", number=50, transform="percent_to_decimal", page=7,
                quotes=["The United States imposed 50% tariffs on approximately $20 billion of Canadian goods Saturday", quote])
    c = build_check(CANADA, f, [FURNITURE_TODAY], "2026-10-10")
    assert c["live"] == pytest.approx(0.5)
    assert c["evidence"][1]["quote"].count("\u201c") == 1 and "\x1c" not in c["evidence"][1]["quote"]


def test_a_page_dated_before_the_model_cannot_make_it_stale():
    # the offline re-run: a 2025 Reuters snippet on another furniture tariff, read as today's Vietnam rate
    reuters = {"id": 1, "url": "https://www.reuters.com/x-2025-09-30/", "date": "2025-09-30", "title": "",
               "text": "25% tariffs on wooden furniture from October 14, which could rise next year to 50% for vanities."}
    opinion = {"id": 3, "url": "https://www.furnituretoday.com/opinion/x", "title": "",
               "text": "Last week, the U.S. Trade Representative launched a Section 301 investigation into Vietnam."}
    f = finding(p_stale=1.0, kind="level", number=0.25, transform="as_is", quotes=[reuters["text"]], page=1,
                events=[{"summary": "tariff", "direction": "raises", "page": 1, "quote": reuters["text"]}])
    c = build_check(VIETNAM, f, [reuters, opinion], "2026-10-10", "2026-08-01")
    assert c["live"] is None
    assert c["status"] == "unknown"
    assert len(c["evidence"]) == 1 and len(c["events"]) == 1  # still shown, they are real quotes
    assert build_check(VIETNAM, f, [{**reuters, "date": "2026-09-30"}, opinion], "2026-10-10", "2026-08-01")["live"] == 0.25
    # an old page may still confirm the value
    old = {**AIRLIFT, "date": "2026-07-24"}
    f = finding(p_stale=0.1, kind="level", number=12.5, transform="percent_to_decimal", quotes=[AIRLIFT["text"]], page=3)
    assert build_check(VIETNAM, f, [old], "2026-10-10", "2026-08-01")["status"] == "current"
    # with no number, an event counts only when its page is dated since the model was built
    event = {"summary": "probe", "direction": "raises", "page": 3, "quote": opinion["text"]}
    f = finding(p_stale=1.0, events=[event])
    for date, status in ((None, "unknown"), ("2026-06-08", "unknown"), ("2026-09-08", "stale")):
        assert build_check(VIETNAM, f, [reuters, {**opinion, "date": date}], "2026-10-10", "2026-08-01")["status"] == status


# --- more FRED series, and a model built from the close before built_on ---------------------------


@pytest.mark.parametrize("label, series", [
    ("USD/JPY exchange rate (yen per $)", "DEXJPUS"),
    ("USD/CAD exchange rate, 27-Feb-2026 (C$ per $)", "DEXCAUS"),
    ("USD/MXN exchange rate", "DEXMXUS"),
    ("USD/BRL exchange rate used for dry-mill costs", "DEXBZUS"),
    ("US Gulf Coast kerosene-type jet fuel spot price ($/gal)", "DJFUELUSGULF"),
    ("On-highway diesel, US average retail ($/gal)", "GASDESW"),
    ("Natural gas, Henry Hub spot ($/MMBtu)", "DHHNGSP"),
    ("Arabica coffee, other mild arabicas (cents/lb)", "PCOFFOTMUSDM"),
    ("30-year fixed mortgage rate (%)", "MORTGAGE30US"),
    ("Brent crude oil price ($/bbl)", "DCOILBRENTEU"),
])
def test_label_maps_to_its_fred_series(label, series):
    from checks.drivers import fred_series_for

    assert fred_series_for(label)[0] == series


def test_anchor_accepts_the_close_before_built_on():
    from checks.drivers import series_scale

    obs = {"series": "DGS10", "unit": "percent", "then": 4.23, "then_recent": [4.34, 4.38, 4.37, 4.23], "now": 5.22}
    label = "Risk-free rate, 10-year US Treasury yield (%)"
    assert series_scale(label, 0.0437, obs) == 0.01  # set at the 31-Jul close, built_on is 1-Aug
    assert series_scale(label, 0.0437, {**obs, "then_recent": [4.23]}) is None
    assert series_scale(label, 0.0437, {k: v for k, v in obs.items() if k != "then_recent"}) is None
    assert series_scale(label, 0.0641, obs) is None  # a rate plus a margin is not the series
