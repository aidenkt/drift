"""The evaluation harness: answer-key parser, scorer and runner. No network, no keys."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))  # eval/ is not part of the installed package

from eval import run, score, text, truth  # noqa: E402

DATA = Path(__file__).parents[2] / "data"
REPORT = Path(__file__).parent / "data" / "report_aug2026.json"
# case -> (workbook, assumptions set, planted, controls, other cells, rows of buried unit constants)
SHAPES = {
    "aug2026": ("case_study_aug2026.xlsx", "2026-08-01", 6, 2, 26, 4),
    "aug2025": ("case_study_aug2025.xlsx", "2025-08-01", 6, 2, 25, 4),
    "airline": ("case_study_airline.xlsx", "2025-05-01", 4, 2, 29, 9),
    "coffee": ("case_study_coffee.xlsx", "2026-05-01", 6, 2, 35, 6),
    "homebuilder": ("case_study_homebuilder.xlsx", "2025-11-01", 4, 2, 34, 8),
    "trucking": ("case_study_trucking.xlsx", "2026-03-01", 5, 2, 36, 5),
}
pytestmark = pytest.mark.skipif(not (DATA / "ground_truth.md").exists(), reason="case study data not present")


@pytest.fixture(scope="module")
def keys():
    return {case: truth.load(run.truth_path(case)) for case in run.CASES}


@pytest.fixture(scope="module")
def scores(keys):
    return score.score(json.loads(REPORT.read_text()), keys["aug2026"])


def _planted(key, cell):
    return next(row for row in key.planted if row.cell == cell)


def _control(key, cell):
    return next(row for row in key.controls if row.cell == cell)


# --- truth -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("case", run.CASES)
def test_every_answer_key_parses_to_the_expected_shape(keys, case):
    key = keys[case]
    workbook, built_on, planted, controls, other_cells, other_rows = SHAPES[case]
    assert (key.workbook, key.built_on) == (workbook, built_on)
    assert (len(key.planted), len(key.controls)) == (planted, controls)
    assert (len(key.other_cells), len(key.other_rows)) == (other_cells, other_rows)
    assert all(row.stale and row.impacts and "ev" in row.impacts for row in key.planted)
    assert all(not row.stale and row.live == row.value for row in key.controls)


def test_aug2026_rows(keys):
    key = keys["aug2026"]
    sofr = _planted(key, "P&L!C35:G35")
    assert (sofr.value, sofr.live, sofr.formula) == (0.0366, 0.0387, "=0.0366+Assumptions!$B$29")
    assert sofr.impacts == {"ebitda": 0.0, "net_income": -0.5, "ev": -5.1}
    assert sofr.alternatives == ()

    freight = _planted(key, "P&L!C18:G18")
    assert (freight.value, freight.live, freight.impacts) == (5739.0, 7624.0, {"ebitda": -18.5, "ev": -212.0})

    tariff = _planted(key, "Assumptions!B23")
    assert (tariff.value, tariff.live, tariff.impacts) == (0.0, 0.5, {"ebitda": -48.1, "ev": -552.4})

    brent = _planted(key, "Assumptions!B20")
    assert (brent.value, brent.live, brent.impacts) == (96.95, 125.44, {"ebitda": -12.0, "ev": -137.3})
    assert brent.alternatives == (truth.Alternative(104.72, {"ebitda": -3.3, "ev": -37.5}),)

    eurusd = _planted(key, "Assumptions!B21")
    assert (eurusd.value, eurusd.live, eurusd.alternatives) == (1.1519, 1.1259, (truth.Alternative(1.1206, None),))
    assert _planted(key, "DCF!B6").impacts == {"ev": -41.5}

    vietnam = _control(key, "Assumptions!B22")
    assert (vietnam.value, vietnam.live, vietnam.stale) == (0.125, 0.125, False)
    assert _control(key, "Assumptions!B24").value == 0.21

    assert key.other[8].cells == ("DCF!B7", "DCF!B8", "DCF!B9", "DCF!B14", "DCF!B16")
    assert key.other[7].cells == tuple(f"Assumptions!{column}33" for column in "BCDEF")
    assert key.other[9].rows == (("P&L", 18), ("P&L", 20), ("DCF", 28), ("DCF", 30))
    assert "Assumptions!B29" in key.other_cells and "Assumptions!B20" not in key.other_cells


def test_aug2025_rows(keys):
    key = keys["aug2025"]
    sofr = _planted(key, "P&L!C33:G33")
    assert (sofr.value, sofr.live, sofr.impacts) == (0.0439, 0.0387, {"ebitda": 0.0, "net_income": 1.3, "ev": 16.8})
    vietnam = _planted(key, "Assumptions!B21")
    assert (vietnam.value, vietnam.live, vietnam.impacts) == (0.2, 0.125, {"ebitda": 13.1, "ev": 154.2})
    canada = _planted(key, "Assumptions!B22")
    assert (canada.value, canada.live) == (0.0, 0.5)
    brent = _planted(key, "Assumptions!B19")
    assert brent.alternatives == (truth.Alternative(104.72, {"ebitda": -12.7, "ev": -148.8}),)
    assert _planted(key, "P&L!C16:G16").formula == "=C15*2632/1000000"
    assert (_control(key, "Assumptions!B20").value, _control(key, "Assumptions!B20").live) == (0.0, 0.0)
    assert key.other[4].cells == tuple(f"Assumptions!B{row}" for row in range(12, 17))


def test_airline_rows(keys):
    key = keys["airline"]
    fuel = _planted(key, "Assumptions!B14")
    assert (fuel.value, fuel.live, fuel.impacts) == (1.909, 4.342, {"ebitda": -551.9, "ev": -6956.4})
    yen = _planted(key, "P&L!C14:G14")
    assert (yen.value, yen.live, yen.formula) == (142.63, 157.81, "=C13*1000/142.63")
    assert _planted(key, "Assumptions!B33").impacts == {"ebitda": 0.0, "net_income": 18.4, "ev": 239.4}
    assert _control(key, "Assumptions!B15").value == 0.075
    assert key.other[5].cells == ("Assumptions!B31", "Assumptions!B32", "Assumptions!B34", "Assumptions!B35")
    assert key.other[8].rows[:5] == tuple(("P&L", row) for row in (10, 14, 20, 23, 24))
    assert key.other[8].rows[5:] == tuple(("DCF", row) for row in (5, 19, 28, 30))


def test_coffee_rows(keys):
    key = keys["coffee"]
    arabica = _planted(key, "Assumptions!B23")
    assert (arabica.value, arabica.live, arabica.impacts) == (334.11, 359.16, {"ebitda": -29.6, "ev": -382.7})
    assert arabica.alternatives == (truth.Alternative(289.05, {"ebitda": 53.2, "ev": 688.4}),)
    real = _planted(key, "P&L!C16:G16")
    assert (real.value, real.live, real.formula) == (4.9792, 5.2222, "=C15/4.9792")
    assert _planted(key, "Assumptions!B24").impacts == {"ebitda": -0.2, "ev": -2.1}
    assert _planted(key, "Assumptions!B32").impacts == {"ebitda": 0.0, "net_income": -0.6, "ev": -11.6}
    assert (_control(key, "Assumptions!B26").value, _control(key, "Assumptions!B26").live) == (0.0, 0.0)
    growth = key.other[5].cells
    assert len(growth) == 10 and growth[0] == "Assumptions!B37" and growth[-1] == "Assumptions!F38"


def test_homebuilder_rows(keys):
    key = keys["homebuilder"]
    mortgage = _planted(key, "Assumptions!B16")
    assert (mortgage.value, mortgage.live, mortgage.impacts) == (0.0617, 0.074, {"ebitda": -123.1, "ev": -1293.8})
    limit = _planted(key, "Assumptions!B18")
    assert (limit.value, limit.live, limit.impacts) == (806500.0, 832750.0, {"ebitda": 0.0, "ev": 0.0})
    sofr = _planted(key, "P&L!C33:G33")
    assert (sofr.value, sofr.formula) == (0.0422, "=Assumptions!$B$29*(0.0422+Assumptions!$B$30)")
    assert sofr.impacts == {"ebitda": 0.0, "net_income": 1.1, "ev": 11.4}
    assert (_control(key, "Assumptions!B17").value, _control(key, "Assumptions!B17").live) == (0.07, 0.07)
    assert key.other[4].cells == tuple(f"Assumptions!B{row}" for row in range(27, 34))


def test_trucking_rows(keys):
    key = keys["trucking"]
    risk_free = _planted(key, "DCF!B9")
    assert (risk_free.value, risk_free.live, risk_free.formula) == (0.0397, 0.0522, "=0.0397+B7*B6+B8")
    assert risk_free.impacts == {"ev": -809.5}
    peso = _planted(key, "P&L!C27:G27")
    assert (peso.value, peso.live, peso.impacts) == (17.2207, 18.192, {"ebitda": 9.8, "ev": 129.1})
    assert _planted(key, "P&L!C38:G38").impacts == {"ebitda": 0.0, "net_income": -1.6, "ev": -58.8}
    assert _planted(key, "Assumptions!B24").impacts == {"ebitda": -7.6, "ev": -125.9}
    assert (_control(key, "Assumptions!B26").value, _control(key, "Assumptions!B26").live) == (550.0, 550.0)
    assert key.other[6].cells == ("DCF!B6", "DCF!B7", "DCF!B8", "DCF!B13", "DCF!B15")
    assert key.other[7].rows == (("P&L", 25), ("DCF", 5), ("DCF", 18), ("DCF", 27), ("DCF", 29))


@pytest.mark.parametrize(
    "old, new, complaint",
    [
        ("EBITDA unchanged, net income -$0.5M, EV -$5.1M", "EBITDA flat, net income -$0.5M, EV -$5.1M", "impacts not fully understood"),
        ("Yes; +47bp. EV -$41.5M", "Yes; +47bp. EV about -$41.5M", "impacts not fully understood"),
        ("Yes; +47bp. EV -$41.5M", "Yes; +74bp. EV -$41.5M", "drift +74bp does not match"),
        ("Yes; +47bp. EV -$41.5M", "Yes. EV -$41.5M", "no drift"),
        ("Yes; +47bp. EV -$41.5M", "Probably; +47bp. EV -$41.5M", "should be stale"),
        ("| 4.75% ([FRED DGS10]", "| 4.75 ([FRED DGS10]", "not all percents"),
        ("| 4.75% ([FRED DGS10]", "| about 4.75% ([FRED DGS10]", "does not open with a plain number"),
        ("| DCF!B6 |", "| the risk-free rate on DCF |", "cell is not"),
        ("=0.0366+Assumptions!$B$29", "=0.0386+Assumptions!$B$29", "is not a literal in"),
        ("(-$3.3M and -$37.5M on the future)", "(-$3.3M on the future)", "on the future"),
    ],
)
def test_a_planted_row_the_parser_cannot_read_fails_naming_the_file_and_the_row(tmp_path, old, new, complaint):
    original = (DATA / "ground_truth.md").read_text()
    assert original.count(old) == 1
    path = tmp_path / "broken.md"
    path.write_text(original.replace(old, new))
    with pytest.raises(truth.TruthError, match=r"broken\.md: planted row \d ") as error:
        truth.load(path)
    assert complaint in str(error.value)


@pytest.mark.parametrize(
    "old, new, complaint",
    [
        ("| 12.5%, unchanged.", "| 15.0%, raised.", "control row 1 (Assumptions!B22): a control's live value"),
        ("| No (fresh control); 0.0% |\n| Assumptions!B24", "| Yes |\n| Assumptions!B24", "(Assumptions!B22): a control should not be stale"),
        ("| DCF!B7:B9, B14, B16 |", "| DCF!B7 to B16 |", "other row 9 (DCF!B7 to B16): cell is neither"),
        ("| Assumptions!B5 | FY2025A", "| Assumptions!B20 | FY2025A", "listed more than once: Assumptions!B20"),
        ("| Cell | Driver | Value in model |\n", "| Cell | Value in model |\n", "other table has columns"),
        ("## Controls (should not be flagged)", "## Checks", "expected one '## Controls' section"),
        ("(assumptions set 2026-08-01,", "(set in August,", "no 'Workbook:"),
    ],
)
def test_other_things_the_parser_cannot_read_fail_too(tmp_path, old, new, complaint):
    original = (DATA / "ground_truth.md").read_text()
    assert original.count(old) == 1
    path = tmp_path / "broken.md"
    path.write_text(original.replace(old, new))
    with pytest.raises(truth.TruthError) as error:
        truth.load(path)
    assert complaint in str(error.value) and "broken.md" in str(error.value)


# --- score -----------------------------------------------------------------------------------------


def test_saved_real_report_scores_as_read_by_eye(scores):
    planted = {p["cell"]: p for p in scores["planted"]}
    assert all(p["found"] and p["stale"] for p in planted.values())
    assert {cell for cell, p in planted.items() if p["has_live"]} == {"P&L!C35:G35", "Assumptions!B20", "P&L!C18:G18"}
    assert {cell for cell, p in planted.items() if p["live_ok"]} == {"P&L!C35:G35", "Assumptions!B20"}

    sofr, brent, freight = planted["P&L!C35:G35"], planted["Assumptions!B20"], planted["P&L!C18:G18"]
    assert (sofr["live"], sofr["matched"], sofr["impact_ok"]) == (0.0387, "primary", True)
    assert [(i["kind"], i["output"], i["ok"]) for i in sofr["impacts"]] == [
        ("ebitda", "P&L!C27", True),  # unchanged: the engine lists no change for it
        ("net_income", "P&L!C39", True),
        ("ev", "DCF!B38", True),
    ]
    assert sofr["impacts"][0]["delta"] == 0.0
    assert (brent["live"], brent["matched"], brent["impact_ok"]) == (125.44, "primary", True)
    # 7960 against 7624 is 4.4% out, so its impact cannot be compared with the key's
    assert (freight["live"], freight["live_ok"], freight["impact_ok"], freight["impacts"]) == (7960.0, False, None, [])
    assert freight["engine"]["label"].startswith("Ocean freight") and freight["engine"]["impact"]["P&L!C27"] < -18.5
    assert planted["DCF!B6"]["impact_ok"] is None

    controls = {c["cell"]: c for c in scores["controls"]}
    assert (controls["Assumptions!B22"]["stale"], controls["Assumptions!B22"]["ok"]) == (True, False)
    assert (controls["Assumptions!B24"]["stale"], controls["Assumptions!B24"]["ok"]) == (False, True)

    assert [(f["cell"], f["kind"]) for f in scores["false_positives"]] == [
        ("Assumptions!B22", "control"),
        ("Assumptions!B29", "other"),
        ("DCF!B8", "other"),
    ]
    assert scores["false_positives"][1]["label"] == "Term loan margin over SOFR (%)"
    assert {o["cell"] for o in scores["other"] if o["stale"]} == {"Assumptions!B29", "DCF!B8"}
    assert {o["cell"] for o in scores["other"] if o["market"]} == {"Assumptions!B29", "DCF!B8"}
    # 26 listed cells and the four unit constants buried in the listed rows; the planted 5739 in row 18 is not one
    assert len(scores["other"]) == 30 and all(o["found"] for o in scores["other"])
    assert [(o["cell"], o["value"]) for o in scores["other"][26:]] == [
        ("P&L!C18:G18", 1000000.0),
        ("P&L!C20:G20", 1000.0),
        ("DCF!C28:G28", 365.0),
        ("DCF!C30:G30", 365.0),
    ]


def test_totals_and_headline_of_the_saved_real_report(scores):
    totals = scores["totals"]
    assert (totals["planted"], totals["found"], totals["stale"], totals["has_live"], totals["live_ok"]) == (6, 6, 6, 3, 2)
    assert (totals["impact_checked"], totals["impact_ok"]) == (2, 2)
    assert (totals["controls"], totals["controls_ok"], totals["false_positives"]) == (2, 1, 3)
    assert (totals["recall"], totals["live_accuracy"], totals["impact_accuracy"]) == (1.0, pytest.approx(1 / 3), 1.0)
    assert scores["headline"] == (
        "planted 6/6 found, 6/6 stale, 2/6 live ok, 2/2 impact ok; controls 1/2 ok; 3 false positives (controls: 1)"
    )


def test_tolerances():
    assert score.live_ok(7700, 7624) and not score.live_ok(7960, 7624)  # 2% relative
    assert score.live_ok(0.0392, 0.0387) and not score.live_ok(0.0393, 0.0387)  # 5bp under 0.2
    assert score.live_ok(0.0, 0.0) and not score.live_ok(0.001, 0.0)
    assert score.live_ok(0.51, 0.5) and not score.live_ok(0.52, 0.5)
    assert score.impact_ok(-0.6, -0.5) and not score.impact_ok(-0.7, -0.5)  # 0.15 absolute
    assert score.impact_ok(-555, -552.4) and not score.impact_ok(-570, -552.4)  # 2% once that is larger


def _report(*constants):
    outputs = [
        {"cell": "DCF!B40", "label": "EBITDA", "value": 1.0},
        {"cell": "P&L!C28", "label": "EBITDA margin", "value": 0.1},
        {"cell": "P&L!C27", "label": "ebitda", "value": 106.0},
        {"cell": "P&L!C39", "label": "Net income", "value": 54.0},
        {"cell": "DCF!B38", "label": "Enterprise value (NPV)", "value": 905.0},
        {"cell": "DCF!B42", "label": "Implied EV / FY2026E EBITDA", "value": 8.5},
    ]
    return {"outputs": outputs, "constants": list(constants)}


def _constant(cell, value, status=None, live=None, impact=(), **extra):
    check = {"kind": "series", "status": status, "live": live} if status else None
    return {"cell": cell, "value": value, "label": "", "check": check, "impact": [{"output": o, "delta": d} for o, d in impact]} | extra


def test_outputs_are_picked_by_label_on_the_pnl_sheet():
    assert score.output_cells(_report()) == {"ebitda": "P&L!C27", "net_income": "P&L!C39", "ev": "DCF!B38"}


def test_an_alternative_live_value_is_scored_against_its_own_impacts(keys):
    future = _constant("Assumptions!B20", 96.95, "stale", 104.72, [("P&L!C27", -3.26), ("DCF!B38", -37.45)])
    brent = score.score(_report(future), keys["aug2026"])["planted"][2]
    assert (brent["live_ok"], brent["matched"], brent["impact_ok"]) == (True, "alternative", True)
    assert [i["expected"] for i in brent["impacts"]] == [-3.3, -37.5]

    # the key prices only the H.10 print; the market close is the nearer match and is scaled from it
    close = _constant("Assumptions!B21", 1.1519, "stale", 1.1206, [("P&L!C27", 2.32), ("DCF!B38", 26.58)])
    eurusd = score.score(_report(close), keys["aug2026"])["planted"][3]
    assert (eurusd["live_ok"], eurusd["matched"], eurusd["impact_ok"]) == (True, "alternative", True)
    assert eurusd["impacts"][0]["expected"] == 1.9 and eurusd["impacts"][0]["expected_at_live"] == pytest.approx(2.287, abs=0.001)


def test_expected_impact_follows_a_live_value_inside_the_tolerance(keys):
    def sofr(net_income, ev):
        group = [f"P&L!{column}35" for column in "CDEFG"]
        constant = _constant("P&L!C35:G35", 0.0366, "stale", 0.039, [("P&L!C39", net_income), ("DCF!B38", ev)], cells=group)
        return score.score(_report(constant), keys["aug2026"])["planted"][0]

    # 3.90% is 24bp of drift where the key has 21bp, so the key's -0.5 and -5.1 become -0.57 and -5.83
    right = sofr(-0.56, -5.82)
    assert (right["live_ok"], right["matched"], right["impact_ok"]) == (True, "primary", True)
    assert [i["expected_at_live"] for i in right["impacts"]] == [0.0, pytest.approx(-0.5714, abs=1e-4), pytest.approx(-5.8286, abs=1e-4)]
    assert sofr(-0.5, -5.1)["impact_ok"] is False


def test_a_wrong_impact_is_caught(keys):
    spot = _constant("Assumptions!B20", 96.95, "stale", 125.44, [("P&L!C27", -12.0), ("DCF!B38", -120.0)])
    brent = score.score(_report(spot), keys["aug2026"])["planted"][2]
    assert (brent["live_ok"], brent["impact_ok"]) == (True, False)
    assert [(i["kind"], i["ok"]) for i in brent["impacts"]] == [("ebitda", True), ("ev", False)]

    silent = _constant("Assumptions!B20", 96.95, "stale", 125.44)
    assert score.score(_report(silent), keys["aug2026"])["planted"][2]["impact_ok"] is False


def test_matching_is_by_cell_and_value(keys):
    group = ["P&L!C18", "P&L!D18", "P&L!E18", "P&L!F18", "P&L!G18"]
    unit = _constant("P&L!C18:G18", 1000000.0, "stale", embedded=True, cells=group, literal_index=1)
    freight = _constant("P&L!C18:G18", 5739.0, "current", embedded=True, cells=group, literal_index=0)
    merged = _constant("DCF!B6:C6", 0.0475, "stale", embedded=True, cells=["DCF!B6", "DCF!C6"])
    wrong_value = _constant("Assumptions!B23", 0.1, "stale")
    scores = score.score(_report(unit, freight, merged, wrong_value), keys["aug2026"])
    planted = {p["cell"]: p for p in scores["planted"]}

    assert (planted["P&L!C18:G18"]["found"], planted["P&L!C18:G18"]["stale"]) == (True, False)
    assert planted["P&L!C18:G18"]["engine"]["value"] == 5739.0
    assert planted["DCF!B6"]["found"] and planted["DCF!B6"]["engine"]["cell"] == "DCF!B6:C6"
    assert not planted["Assumptions!B23"]["found"] and not planted["P&L!C35:G35"]["found"]
    assert [(f["cell"], f["value"], f["kind"]) for f in scores["false_positives"]] == [
        ("P&L!C18:G18", 1000000.0, "other"),
        ("Assumptions!B23", 0.1, "unlisted"),
    ]
    assert scores["totals"]["found"] == 2 and scores["totals"]["stale"] == 1


# --- run -------------------------------------------------------------------------------------------


def test_graph_only_scores_every_planted_driver_found_with_the_expected_impact(tmp_path, capsys):
    assert run.main(["--graph-only", "--json", str(tmp_path / "scores.json"), "--out", str(tmp_path / "reports")]) == 0
    summary = json.loads((tmp_path / "scores.json").read_text())
    assert summary["mode"] == "graph-only" and list(summary["cases"]) == list(run.CASES)
    for case, result in summary["cases"].items():
        planted = result["scores"]["planted"]
        assert len(planted) == SHAPES[case][2]
        assert [p["cell"] for p in planted if not (p["found"] and p["impact_ok"])] == [], case
        assert result["scores"]["totals"]["controls_found"] == 2
        assert json.loads((tmp_path / "reports" / f"{case}.json").read_text())["built_on"] == SHAPES[case][1]
    assert summary["totals"]["planted"] == summary["totals"]["found"] == summary["totals"]["impact_ok"] == 31

    printed = capsys.readouterr().out
    assert "total             31  31/31      31/31           12/12" in printed
    assert "=> planted 5/5 found, 5/5 impact ok at the expected live value" in printed


@pytest.mark.parametrize("case", ["aug2026", "aug2025", "coffee"])
def test_the_graph_reproduces_the_impacts_of_alternative_live_values(keys, case):
    from graph import constants, impact, parse

    key = keys[case]
    wb = parse.load(DATA / key.workbook)
    graph = parse.build_graph(wb)
    found, outputs = constants.find(wb, graph), constants.find_outputs(wb, graph)
    cells = score.output_cells({"outputs": outputs})
    priced = [(row, alt) for row in key.planted for alt in row.alternatives if alt.impacts]
    assert priced
    for row, alt in priced:
        constant = dict(score.find(found, row.cell, row.value), check={"status": "stale", "live": alt.live})
        moved = {d["output"]: d["delta"] for d in impact.deltas(wb, graph, constant, outputs)}
        for kind, delta in alt.impacts.items():
            assert moved.get(cells[kind], 0.0) == pytest.approx(delta, abs=0.05)


def test_scoring_a_saved_report_from_the_command_line(tmp_path, capsys):
    out = tmp_path / "scores.json"
    assert run.main(["--report", str(REPORT), "--truth", str(DATA / "ground_truth.md"), "--json", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "=> planted 6/6 found, 6/6 stale, 2/6 live ok, 2/2 impact ok; controls 1/2 ok; 3 false positives" in printed
    assert "off +4.4%" in printed and "STALE" in printed
    summary = json.loads(out.read_text())
    assert summary["mode"] == "report" and summary["totals"]["live_ok"] == 2


def test_a_real_run_passes_the_answer_keys_date_and_saves_the_report(tmp_path, monkeypatch):
    import pipeline

    calls = []

    def fake_run(path, **kwargs):
        calls.append((path, kwargs))
        return json.loads(REPORT.read_text())

    monkeypatch.setattr(pipeline, "run", fake_run)
    monkeypatch.setattr(run, "REPO", tmp_path)  # no .env there: nothing is loaded into this process
    monkeypatch.setattr(run, "_log_to", lambda path: None)
    result = run.run_case("aug2026", tmp_path, graph_only=False)

    expected = {"model_id": "eval-aug2026", "filename": "case_study_aug2026.xlsx", "built_on": "2026-08-01"}
    assert calls == [(DATA / "case_study_aug2026.xlsx", expected)]
    assert result["scores"]["totals"]["live_ok"] == 2 and result["seconds"] >= 0
    assert json.loads((tmp_path / "aug2026.json").read_text())["model_id"] == "real"


def test_a_case_that_raises_is_reported_without_its_keys(tmp_path, monkeypatch):
    import pipeline

    def broken_run(path, **kwargs):
        raise RuntimeError("401 for url https://example.test/?api_key=sk-not-a-real-key")

    monkeypatch.setenv("FRED_API_KEY", "sk-not-a-real-key")
    monkeypatch.setattr(pipeline, "run", broken_run)
    monkeypatch.setattr(run, "REPO", tmp_path)
    monkeypatch.setattr(run, "_log_to", lambda path: None)
    failed = run.run_case("airline", tmp_path, graph_only=False)

    assert failed["error"] == "RuntimeError: 401 for url https://example.test/?api_key=***"
    assert "sk-not-a-real-key" not in failed["traceback"] and "broken_run" in failed["traceback"]
    assert "scores" not in failed and not (tmp_path / "airline.json").exists()

    results = {"airline": failed, "trucking": run.run_case("trucking", None, graph_only=True)}
    table = text.overall(results)
    rows = {line.split()[0]: line.split()[1:] for line in table.split("\n")}
    assert rows["airline"][0] == "FAILED" and rows["failed:"] == ["airline"]
    assert rows["trucking"][:5] == ["5", "5/5", "5/5", "5/5", "5/5"]
    assert text.scorecard("airline", failed).startswith("airline  FAILED")
