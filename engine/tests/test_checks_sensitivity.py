"""Sensitivity on the real case-study workbook, recalculated with graph's engine."""

from pathlib import Path

import pytest

from checks import sensitivity
from graph import constants, parse

XLSX = Path(__file__).parents[2] / "data" / "case_study_aug2026.xlsx"
pytestmark = pytest.mark.skipif(not XLSX.exists(), reason="case study workbook missing")


@pytest.fixture(scope="module")
def model():
    wb = parse.load(XLSX)
    graph = parse.build_graph(wb)
    return wb, graph, {c["cell"]: c for c in constants.find(wb, graph) if c.get("literal_index", 0) == 0}


def _delta(s, label):
    return next(o["delta"] for o in s["outputs"] if o["label"] == label)


def test_stronger_euro_lowers_ebitda(model):
    wb, graph, found = model
    s = sensitivity.for_constant(found["Assumptions!B21"], wb, graph)
    assert s["change"] == "+10%"
    assert s["to"] == pytest.approx(1.1519 * 1.1)
    assert _delta(s, "EBITDA") < 0  # EU suppliers price in euros
    assert _delta(s, "Enterprise value (NPV)") < 0


def test_zero_tariff_is_bumped_one_point(model):
    wb, graph, found = model
    s = sensitivity.for_constant(found["Assumptions!B23"], wb, graph)
    assert s["from"] == 0 and s["to"] == pytest.approx(0.01)
    assert _delta(s, "EBITDA") < 0


def test_buried_freight_rate_has_a_sensitivity(model):
    wb, graph, found = model
    s = sensitivity.for_constant(found["P&L!C18:G18"], wb, graph)
    assert _delta(s, "EBITDA") < 0
