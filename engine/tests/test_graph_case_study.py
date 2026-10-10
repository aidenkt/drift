"""Graph half against data/ground_truth.md: the planted constants are found and their impacts match."""

import os
from pathlib import Path

import pytest

from graph import constants, impact, parse

XLSX = Path(os.environ.get("DRIFT_CASE_STUDY") or Path(__file__).parents[2] / "data" / "case_study_aug2026.xlsx")
pytestmark = pytest.mark.skipif(not XLSX.exists(), reason="case study workbook not present")

EBITDA, NET_INCOME, EV = "P&L!C27", "P&L!C39", "DCF!B38"

# (cell, value in model, live value, {output: expected change in $M}) from the ground-truth table
PLANTED = [
    ("P&L!C35:G35", 0.0366, 0.0387, {EBITDA: 0.0, NET_INCOME: -0.5, EV: -5.1}),
    ("DCF!B6", 0.0475, 0.0522, {EV: -41.5}),
    ("Assumptions!B20", 96.95, 125.44, {EBITDA: -12.0, EV: -137.3}),
    ("Assumptions!B21", 1.1519, 1.1259, {EBITDA: 1.9, EV: 22.1}),
    ("P&L!C18:G18", 5739, 7624, {EBITDA: -18.5, EV: -212.0}),
    ("Assumptions!B23", 0.0, 0.5, {EBITDA: -48.1, EV: -552.4}),
]
CONTROLS = ["Assumptions!B22", "Assumptions!B24"]


@pytest.fixture(scope="module")
def case():
    wb = parse.load(XLSX)
    graph = parse.build_graph(wb)
    outputs = constants.find_outputs(wb, graph)
    found = {(c["cell"], c["value"]): c for c in constants.find(wb, graph)}
    return wb, graph, outputs, found


def test_headline_outputs(case):
    _, _, outputs, _ = case
    values = {o["cell"]: o["value"] for o in outputs}
    assert values[EBITDA] == pytest.approx(106.0, abs=0.05)
    assert values[EV] == pytest.approx(905.5, abs=0.05)
    assert NET_INCOME in values


@pytest.mark.parametrize("cell, value, live, expected", PLANTED)
def test_planted_constant_is_found_with_the_expected_impact(case, cell, value, live, expected):
    wb, graph, outputs, found = case
    constant = dict(found[(cell, value)], check={"kind": "series", "status": "stale", "live": live})
    moved = {d["output"]: d["delta"] for d in impact.deltas(wb, graph, constant, outputs)}
    for output, delta in expected.items():
        assert moved.get(output, 0.0) == pytest.approx(delta, abs=0.05)


def test_controls_and_unit_conversions_are_found(case):
    _, _, _, found = case
    cells = {cell for cell, _ in found}
    assert set(CONTROLS) <= cells
    assert ("P&L!C18:G18", 1000000) in found and ("P&L!C20:G20", 1000) in found


def test_all_planted_changes_together(case):
    wb, graph, outputs, found = case
    live = [dict(found[(cell, value)], check={"live": new}) for cell, value, new, _ in PLANTED]
    moved = {d["output"]: d["delta"] for d in impact.combined(wb, graph, live, outputs)}
    assert moved[EBITDA] == pytest.approx(-12.0 + 1.9 - 18.5 - 48.1, abs=0.2)  # EBITDA is linear in these four
    assert moved[EV] < -552.4
