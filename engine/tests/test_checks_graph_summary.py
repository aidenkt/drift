"""Graph summary on the real case-study workbook, built by graph's own parser."""

from pathlib import Path

import pytest

from checks import graph_summary
from graph import constants, parse

XLSX = Path(__file__).parents[2] / "data" / "case_study_aug2026.xlsx"
pytestmark = pytest.mark.skipif(not XLSX.exists(), reason="case study workbook missing")


@pytest.fixture(scope="module")
def model():
    wb = parse.load(XLSX)
    graph = parse.build_graph(wb)
    return wb, graph, {c["cell"]: c for c in constants.find(wb, graph) if c.get("literal_index", 0) == 0}


def test_brent_reaches_ebitda_through_oil_cost(model):
    wb, graph, found = model
    summary = graph_summary.summarize(found["Assumptions!B20"], wb, graph)
    ebitda = next(p for p in summary["paths"] if p["output_label"] == "EBITDA")
    assert ebitda["cells"][0] == "Assumptions!B20"
    assert ebitda["cells"][-1] == "P&L!C27"
    assert len(ebitda["path"]) >= 3  # input, at least one line item, EBITDA
    assert len(summary["paths"]) == len(found["Assumptions!B20"]["outputs"])


def test_buried_freight_rate_is_combined_with_container_count(model):
    wb, graph, found = model
    summary = graph_summary.summarize(found["P&L!C18:G18"], wb, graph)
    assert summary["combined_with"]  # the container count it multiplies
    assert all(p["cells"][0].startswith("P&L!") and p["cells"][0].endswith("18") for p in summary["paths"])


def test_graph_is_built_once_per_workbook(model):
    wb, _, _ = model
    assert graph_summary.graph_for(wb) is graph_summary.graph_for(wb)
