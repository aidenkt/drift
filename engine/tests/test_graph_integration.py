"""load -> build_graph -> find on a small importer model written to disk."""

from pathlib import Path

import openpyxl
import pytest
from openpyxl.workbook.defined_name import DefinedName

from graph import constants, parse

ASSUMPTIONS = [
    ("EUR/USD rate", 1.08),
    ("SOFR", 0.043),
    ("Revolver spread", 0.0225),
    ("Steel price $/ton", 850),
    ("Container freight $/FEU", 2400),
    ("Import tariff rate", 0.10),
    ("Competitor list price $", 129),
    ("Units sold, base year", 100000),
    ("Steel tons per unit", 0.02),
    ("Units per FEU", 2000),
    ("EUR cost per unit", 45),
    ("Revolver balance $", 5000000),
    ("Opex $", 1500000),
    ("Discount rate", 0.10),
]

PNL = {
    3: ("Price", "=Assumptions!$B$8*0.93"),
    4: ("Revenue", "={c}2*{c}3"),
    5: ("Goods cost", "={c}2*Assumptions!$B$12*Assumptions!$B$2"),
    6: ("Steel", "={c}2*Assumptions!$B$10*Assumptions!$B$5"),
    7: ("Freight", "={c}2/Assumptions!$B$11*Assumptions!$B$6"),
    8: ("Tariff", "={c}5*Assumptions!$B$7"),
    9: ("COGS", "=SUM({c}5:{c}8)"),
    10: ("Gross margin", "={c}4-{c}9"),
    11: ("Opex", "=Assumptions!$B$14"),
    12: ("EBITDA", "={c}10-{c}11"),
    13: ("Interest", "=Assumptions!$B$13*(Assumptions!$B$3+Assumptions!$B$4)"),
    14: ("Net income", "=ROUND(({c}12-{c}13)*(1-0.21),0)"),
}


@pytest.fixture(scope="module")
def model(tmp_path_factory):
    wb = openpyxl.Workbook()
    a = wb.active
    a.title = "Assumptions"
    a.append(("Driver", "Value"))
    for row in ASSUMPTIONS:
        a.append(row)
    wb.defined_names["DiscountRate"] = DefinedName("DiscountRate", attr_text="Assumptions!$B$15")

    p = wb.create_sheet("P&L")
    p.append([None, 2026, 2027, 2028, 2029, 2030])
    p["A2"], p["B2"] = "Units", "=Assumptions!$B$9"
    for prev, col in zip("BCDE", "CDEF"):
        p[f"{col}2"] = f"={prev}2*1.08"
    for row, (label, formula) in PNL.items():
        p.cell(row, 1, label)
        for col in "BCDEF":
            p[f"{col}{row}"] = formula.format(c=col)

    d = wb.create_sheet("DCF Summary")
    d["A2"], d["B2"] = "NPV", "=NPV(DiscountRate,'P&L'!B12:F12)"
    d["A3"], d["B3"] = "Total EBITDA", "=SUM('P&L'!B12:F12)"
    d["A4"], d["B4"] = "Gross margin % 2030", "='P&L'!F10/'P&L'!F4"

    path = tmp_path_factory.mktemp("model") / "importer.xlsx"
    wb.save(path)
    loaded = parse.load(path)
    graph = parse.build_graph(loaded)
    return loaded, graph, {(c["cell"], c.get("literal_index")): c for c in constants.find(loaded, graph)}


def test_outputs(model):
    wb, graph, _ = model
    # the first projection year of each headline row
    assert [o["cell"] for o in constants.find_outputs(wb, graph)] == [
        "P&L!B10",
        "P&L!B12",
        "P&L!B14",
        "DCF Summary!B2",
        "DCF Summary!B3",
        "DCF Summary!B4",
    ]


def test_every_assumption_is_found_and_nothing_else_on_that_sheet(model):
    _, _, found = model
    cells = {cell for cell, _ in found if cell.startswith("Assumptions!")}
    assert cells == {f"Assumptions!B{row}" for row in range(2, 16)}


def test_year_headers_are_not_constants(model):
    _, _, found = model
    assert not any(cell.startswith("P&L!") and cell.endswith("1") for cell, _ in found)


def test_embedded_literals(model):
    _, _, found = model
    embedded = {key: c for key, c in found.items() if c["embedded"]}
    # one constant per row the literal is copied across, not one per cell
    # the 1 in (1-0.21) and the 0 digits argument of ROUND are skipped; 0.21 keeps its token position
    assert list(embedded) == [("P&L!C2:F2", 0), ("P&L!B3:F3", 0), ("P&L!B14:F14", 1)]
    assert [c["value"] for c in embedded.values()] == [1.08, 0.93, 0.21]

    growth = embedded[("P&L!C2:F2", 0)]
    assert growth["formula"] == "=B2*1.08"
    assert growth["cells"] == ["P&L!C2", "P&L!D2", "P&L!E2", "P&L!F2"]
    assert embedded[("P&L!B3:F3", 0)]["cells"] == [f"P&L!{col}3" for col in "BCDEF"]
    assert embedded[("P&L!B14:F14", 1)]["formula"] == "=ROUND((B12-B13)*(1-0.21),0)"


def test_cell_inputs_carry_no_cells(model):
    _, _, found = model
    assert len(found) == 17  # 14 assumptions and 3 grouped literals
    assert not any("cells" in c for c in found.values() if not c["embedded"])


def test_group_reach(model):
    _, _, found = model
    # units from 2027 on, the 9 rows that scale with units in those 4 years, and the 3 summary cells;
    # 2026 has no growth in it, so none of the first-year outputs
    growth = found[("P&L!C2:F2", 0)]
    assert growth["feeds"] == 4 + 9 * 4 + 3
    assert growth["outputs"] == ["DCF Summary!B2", "DCF Summary!B3", "DCF Summary!B4"]

    # price, revenue, gross margin, EBITDA and net income across 5 years, plus the 3 summary cells
    price = found[("P&L!B3:F3", 0)]
    assert price["feeds"] == 5 * 5 + 3
    assert len(price["outputs"]) == 6

    # net income in each year and nothing after it; only the first year is an output
    tax = found[("P&L!B14:F14", 1)]
    assert tax["feeds"] == 5
    assert tax["outputs"] == ["P&L!B14"]


def test_group_keys_resolve_to_context(model):
    wb, _, found = model
    for cell, _ in found:
        assert wb.context(cell)["sheet"] in wb.sheets
    assert wb.context("P&L!C2:F2")["row_label"] == "Units"
    assert wb.context("P&L!C2:F2")["col_header"] == "2027"


def test_reach(model):
    _, _, found = model
    fx = found[("Assumptions!B2", None)]
    # goods cost, tariff, COGS, gross margin, EBITDA, net income across 5 years, plus the 3 summary cells
    assert fx["feeds"] == 33
    assert len(fx["outputs"]) == 6

    sofr = found[("Assumptions!B3", None)]
    assert sofr["feeds"] == 10  # interest and net income across 5 years
    assert sofr["outputs"] == ["P&L!B14"]

    # reached only through SUM ranges and the NPV range
    opex = found[("Assumptions!B14", None)]
    assert opex["outputs"] == ["P&L!B12", "P&L!B14", "DCF Summary!B2", "DCF Summary!B3"]

    # reached only through a defined name
    discount = found[("Assumptions!B15", None)]
    assert discount["feeds"] == 1
    assert discount["outputs"] == ["DCF Summary!B2"]


def test_no_cycles(model):
    _, graph, _ = model
    assert graph.cycles == []


SAVED = Path(__file__).parent / "data" / "Financial Model - P&L and DCF.xlsx"


@pytest.mark.skipif(not SAVED.exists(), reason="saved workbook not present")
def test_saved_workbook_with_cached_values():
    wb = parse.load(SAVED)
    graph = parse.build_graph(wb)
    assert all(wb.values[cell] is not None for cell in wb.formulas)
    assert wb.context("Assumptions!B6")["comment"] == "Spot rate, Jan"

    outputs = {o["label"]: o["value"] for o in constants.find_outputs(wb, graph)}
    # 2026: 100,000 units at 129 * 0.93, less goods 4.86m, tariff 0.486m, steel 1.7m, freight 0.12m, opex 1.5m
    assert outputs["EBITDA"] == pytest.approx(3331000)
    assert outputs["NPV"] == pytest.approx(15488785.26)

    found = constants.find(wb, graph)
    assert len(found) == 17
    assert {c["cell"] for c in found if not c["embedded"]} == {f"Assumptions!B{row}" for row in range(2, 16)}
    assert [c["cell"] for c in found if c["embedded"]] == ["P&L!C2:F2", "P&L!B3:F3", "P&L!B14:F14"]
