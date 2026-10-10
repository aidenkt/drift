import json
from datetime import datetime
from pathlib import Path

import jsonschema
import pytest
from openpyxl.utils import column_index_from_string
from openpyxl.utils.cell import coordinate_from_string

from graph import constants
from graph.parse import Graph, Literal, Workbook
from graph.refs import split_key

SCHEMA = json.loads((Path(__file__).parents[2] / "schema" / "constant.schema.json").read_text())
CONSTANT_SCHEMA = {"$ref": "#/$defs/constant", "$defs": SCHEMA["$defs"]}


def build(cells: dict[str, object], edges=(), literals=(), sheets=None) -> tuple[Workbook, Graph]:
    """cells: {"Sheet!A1": value}; "=..." is a never-calculated formula, ("=...", cached) a calculated one.
    edges: (precedent, dependent) pairs. literals: Literal objects. Sheets default to first-seen order."""
    wb = Workbook(path=Path("x.xlsx"), sheets=list(sheets or []))
    graph = Graph()
    for key, value in cells.items():
        sheet, coord = split_key(key)
        if sheet not in wb.sheets:
            wb.sheets.append(sheet)
        letter, row = coordinate_from_string(coord)
        _, _, max_row, max_col = wb.bounds.get(sheet, (1, 1, 1, 1))
        wb.bounds[sheet] = (1, 1, max(max_row, row), max(max_col, column_index_from_string(letter)))
        if isinstance(value, tuple):
            wb.formulas[key], wb.values[key] = value
        elif isinstance(value, str) and value.startswith("="):
            wb.formulas[key], wb.values[key] = value, None
        else:
            wb.values[key] = value
    for key in wb.formulas:
        graph.precedents[key] = set()
    for precedent, dependent in edges:
        graph.precedents[dependent].add(precedent)
        graph.dependents.setdefault(precedent, set()).add(dependent)
    for literal in literals:
        graph.literals.setdefault(literal.cell, []).append(literal)
    return wb, graph


def find(cells, edges=(), literals=(), sheets=None) -> list[dict]:
    return constants.find(*build(cells, edges, literals, sheets))


def find_outputs(cells, edges=(), literals=(), sheets=None) -> list[dict]:
    return constants.find_outputs(*build(cells, edges, literals, sheets))


def chain_model() -> tuple[Workbook, Graph]:
    """Inputs!B1 -> Model!B2 -> Model!B3 -> P&L!B5 (EBITDA), plus a tax rate that never reaches it."""
    return build(
        {
            "Inputs!A1": "Revenue growth",
            "Inputs!B1": 0.05,
            "Inputs!A2": "Tax rate",
            "Inputs!B2": 0.21,
            "Model!A2": "Revenue",
            "Model!B2": ("=1000*(1+Inputs!B1)", 1050.0),
            "Model!A3": "Contribution",
            "Model!B3": ("=B2*0.4", 420.0),
            "Model!A9": "Tax memo",
            "Model!B9": ("=Inputs!B2*100", 21.0),
            "P&L!A5": "EBITDA",
            "P&L!B5": ("=Model!B3-50", 370.0),
        },
        edges=[
            ("Inputs!B1", "Model!B2"),
            ("Model!B2", "Model!B3"),
            ("Model!B3", "P&L!B5"),
            ("Inputs!B2", "Model!B9"),
        ],
        literals=[
            Literal("Model!B2", 0, 1000.0),
            Literal("Model!B2", 1, 1.0),
            Literal("Model!B3", 0, 0.4),
            Literal("Model!B9", 0, 100.0),
            Literal("P&L!B5", 0, 50.0),
        ],
    )


# --- cell inputs ---


def test_cell_input_with_a_dependent_is_found():
    found = find(
        {"A!A1": "EUR/USD rate", "A!B1": 1.08, "A!A2": "Unused", "A!B2": 5.0, "A!C1": ("=B1*B9", 108.0)},
        edges=[("A!B1", "A!C1")],
    )
    assert found == [
        {
            "cell": "A!B1",
            "value": 1.08,
            "embedded": False,
            "formula": None,
            "label": "",
            "driver": None,
            "label_source": "header",
            "confirmed": False,
            "feeds": 1,
            "outputs": ["A!C1"],
            "check": None,
            "impact": [],
        }
    ]


def test_cell_input_without_a_dependent_is_not_found():
    assert find({"A!A1": "Rate", "A!B1": 1.08, "A!C1": "=B9*2"}) == []
    wb, graph = build({"A!A1": "Rate", "A!B1": 1.08})
    graph.dependents["A!B1"] = set()
    assert constants.find(wb, graph) == []


def test_int_value_becomes_float():
    (found,) = find({"A!A1": "Units", "A!B1": 40, "A!C1": "=B1*2"}, edges=[("A!B1", "A!C1")])
    assert found["value"] == 40.0
    assert isinstance(found["value"], float)
    assert "literal_index" not in found


@pytest.mark.parametrize("value", [True, False, "1.08", "Base case", datetime(2026, 1, 1)])
def test_bool_string_and_datetime_cells_are_not_constants(value):
    assert find({"A!A1": "Input", "A!B1": value, "A!C1": "=B1"}, edges=[("A!B1", "A!C1")]) == []


def test_formula_cell_is_not_a_cell_input():
    found = find(
        {"A!A1": "Rate", "A!B1": ("=B9", 1.08), "A!C1": ("=B1", 1.08)},
        edges=[("A!B1", "A!C1")],
    )
    assert found == []


def test_constant_reached_only_through_a_range():
    found = find(
        {
            "A!A1": "Jan",
            "A!B1": 10.5,
            "A!A2": "Feb",
            "A!B2": 11.5,
            "A!A3": "Mar",
            "A!B3": 12.5,
            "A!A4": "Total",
            "A!B4": ("=SUM(B1:B3)", 34.5),
        },
        edges=[("A!B1", "A!B4"), ("A!B2", "A!B4"), ("A!B3", "A!B4")],
    )
    assert [c["cell"] for c in found] == ["A!B1", "A!B2", "A!B3"]
    assert all(c["feeds"] == 1 and c["outputs"] == ["A!B4"] for c in found)


# --- period headers ---


@pytest.mark.parametrize("value", [1900, 2026, 2026.0, 2100])
def test_year_header_without_a_row_label_is_skipped(value):
    assert find({"A!B1": value, "A!A2": "Revenue", "A!B2": "=B1*2"}, edges=[("A!B1", "A!B2")]) == []


@pytest.mark.parametrize("label", ["Fiscal year", "Year", "FY", "Period", "period ending", "Start date"])
def test_year_on_a_period_row_is_skipped(label):
    assert find({"A!A1": label, "A!B1": 2026, "A!B2": "=B1+1"}, edges=[("A!B1", "A!B2")]) == []


@pytest.mark.parametrize("label", ["Units", "Headcount", "Yearly churn", "Update cost"])
def test_year_sized_value_on_a_labelled_row_is_kept(label):
    (found,) = find({"A!A1": label, "A!B1": 2000, "A!B2": "=B1*3"}, edges=[("A!B1", "A!B2")])
    assert found["cell"] == "A!B1"
    assert found["value"] == 2000.0


@pytest.mark.parametrize("value", [1899, 2101, 2026.5, 12])
def test_unlabelled_number_outside_the_year_range_is_kept(value):
    (found,) = find({"A!B1": value, "A!B2": "=B1*3"}, edges=[("A!B1", "A!B2")])
    assert found["value"] == float(value)


def test_only_the_year_header_of_a_time_series_is_dropped():
    found = find(
        {
            "A!B1": 2025,
            "A!C1": 2026,
            "A!A2": "Units",
            "A!B2": 1950,
            "A!C2": 2000,
            "A!A3": "Label",
            "A!B3": '=B1&": "&B2',
            "A!C3": '=C1&": "&C2',
        },
        edges=[("A!B1", "A!B3"), ("A!B2", "A!B3"), ("A!C1", "A!C3"), ("A!C2", "A!C3")],
    )
    assert [c["cell"] for c in found] == ["A!B2", "A!C2"]


# --- embedded literals ---


def test_embedded_literal():
    found = find(
        {"M!A5": "Revenue EUR", "M!B5": 100.0, "M!C5": ("=B5*1.08", 108.0), "M!D5": ("=C5", 108.0)},
        edges=[("M!B5", "M!C5"), ("M!C5", "M!D5")],
        literals=[Literal("M!C5", 0, 1.08)],
    )
    assert [c["cell"] for c in found] == ["M!B5", "M!C5"]
    assert found[0]["feeds"] == 2
    assert found[1] == {
        "cell": "M!C5",
        "value": 1.08,
        "embedded": True,
        "formula": "=B5*1.08",
        "label": "",
        "driver": None,
        "label_source": "header",
        "confirmed": False,
        "feeds": 2,
        "outputs": ["M!D5"],
        "check": None,
        "impact": [],
        "literal_index": 0,
    }


def test_embedded_literal_in_a_cell_nothing_reads_feeds_itself():
    (found,) = find({"M!A1": "Fee", "M!B1": "=2400*12"}, literals=[Literal("M!B1", 0, 2400.0)])
    assert found["feeds"] == 1
    assert found["outputs"] == ["M!B1"]


def test_two_literals_in_one_formula_keep_their_own_index():
    found = find(
        {"M!A1": "Cost", "M!B1": 10.0, "M!C1": "=B1*2400+350"},
        edges=[("M!B1", "M!C1")],
        literals=[Literal("M!C1", 1, 350.0), Literal("M!C1", 0, 2400.0)],
    )
    embedded = [c for c in found if c["embedded"]]
    assert [(c["literal_index"], c["value"]) for c in embedded] == [(0, 2400.0), (1, 350.0)]
    assert embedded[0]["formula"] == embedded[1]["formula"] == "=B1*2400+350"
    assert embedded[0]["outputs"] is not embedded[1]["outputs"]


def test_zero_one_and_minus_one_are_skipped():
    found = find(
        {"M!A1": "Adj", "M!B1": "=IF(A9>0,A9*1,-1)+0.5-1.0"},
        literals=[
            Literal("M!B1", 0, 0),
            Literal("M!B1", 1, 1),
            Literal("M!B1", 2, -1),
            Literal("M!B1", 3, 0.5),
            Literal("M!B1", 4, -1.0, None, None),
        ],
    )
    assert [(c["literal_index"], c["value"]) for c in found] == [(3, 0.5)]


@pytest.mark.parametrize("value", [12, 100, 365, 1000, -5, 0.05, 2])
def test_no_other_value_based_skips(value):
    (found,) = find({"M!B1": "=A9*12"}, literals=[Literal("M!B1", 0, value)])
    assert found["value"] == float(value)


def test_round_digits_skipped_but_first_argument_kept():
    found = find(
        {"M!B1": "=ROUND(A9*1.08,2)"},
        literals=[Literal("M!B1", 0, 1.08, "ROUND", 0), Literal("M!B1", 1, 2, "ROUND", 1)],
    )
    assert [(c["literal_index"], c["value"]) for c in found] == [(0, 1.08)]


def test_vlookup_column_index_skipped():
    found = find(
        {"M!B1": "=VLOOKUP(A9,D1:F9,3,FALSE)*1.5"},
        literals=[Literal("M!B1", 0, 3, "VLOOKUP", 2), Literal("M!B1", 1, 1.5)],
    )
    assert [(c["literal_index"], c["value"]) for c in found] == [(1, 1.5)]


@pytest.mark.parametrize(
    "func, arg",
    [
        ("ROUND", 1),
        ("ROUNDUP", 1),
        ("ROUNDDOWN", 1),
        ("TRUNC", 1),
        ("FIXED", 1),
        ("MROUND", 1),
        ("CEILING", 1),
        ("FLOOR", 1),
        ("VLOOKUP", 2),
        ("VLOOKUP", 3),
        ("HLOOKUP", 2),
        ("HLOOKUP", 3),
        ("INDEX", 1),
        ("INDEX", 2),
        ("MATCH", 2),
        ("OFFSET", 1),
        ("OFFSET", 2),
        ("OFFSET", 3),
        ("OFFSET", 4),
        ("LEFT", 1),
        ("RIGHT", 1),
        ("MID", 1),
        ("MID", 2),
        ("CHOOSE", 0),
        ("LARGE", 1),
        ("SMALL", 1),
        ("DATE", 0),
        ("DATE", 1),
        ("DATE", 2),
        ("EDATE", 1),
        ("EOMONTH", 1),
        ("TEXT", 1),
        ("RANK", 2),
        ("SUBTOTAL", 0),
        ("AGGREGATE", 0),
    ],
)
def test_structural_arguments_are_skipped(func, arg):
    assert find({"M!B1": "=A9"}, literals=[Literal("M!B1", 0, 7, func, arg)]) == []


@pytest.mark.parametrize(
    "func, arg",
    [
        (None, None),
        ("ROUND", 0),
        ("MROUND", 0),
        ("VLOOKUP", 0),
        ("CHOOSE", 1),
        ("EDATE", 0),
        ("YEAR", 0),
        ("MONTH", 0),
        ("DAY", 0),
        ("IFERROR", 0),
        ("IFERROR", 1),
        ("IF", 2),
        ("MAX", 1),
        ("SUBTOTAL", 1),
    ],
)
def test_other_arguments_are_kept(func, arg):
    (found,) = find({"M!B1": "=A9"}, literals=[Literal("M!B1", 0, 7, func, arg)])
    assert found["value"] == 7.0


# --- feeds, outputs, ordering ---


def test_feeds_and_outputs_on_a_three_level_chain():
    found = constants.find(*chain_model())
    summary = [(c["cell"], c["value"], c["embedded"], c["feeds"], c["outputs"]) for c in found]
    assert summary == [
        ("Inputs!B1", 0.05, False, 3, ["P&L!B5"]),
        ("Inputs!B2", 0.21, False, 1, []),
        ("Model!B2", 1000.0, True, 3, ["P&L!B5"]),
        ("Model!B3", 0.4, True, 2, ["P&L!B5"]),
        ("Model!B9", 100.0, True, 1, []),
        ("P&L!B5", 50.0, True, 1, ["P&L!B5"]),
    ]


def test_outputs_follow_find_outputs_order():
    found = find(
        {
            "DCF!A2": "NPV",
            "DCF!B2": ("=In!B1*3", 3.0),
            "P&L!A9": "EBITDA",
            "P&L!B9": ("=In!B1*2", 2.0),
            "P&L!A4": "Gross margin",
            "P&L!B4": ("=In!B1*4", 4.0),
            "In!A1": "FX",
            "In!B1": 1.08,
        },
        edges=[("In!B1", "DCF!B2"), ("In!B1", "P&L!B9"), ("In!B1", "P&L!B4")],
        sheets=["In", "P&L", "DCF"],
    )
    assert found[0]["cell"] == "In!B1"
    assert found[0]["outputs"] == ["P&L!B4", "P&L!B9", "DCF!B2"]


def test_constants_come_back_in_workbook_order():
    found = find(
        {
            "Two!A1": "x",
            "Two!B1": 5.5,
            "One!A10": "x",
            "One!B10": 4.5,
            "One!AA2": 3.5,
            "One!A2": "x",
            "One!C2": "=B10+7",
            "One!B2": 2.5,
            "One!AB2": "=AA2+B2+Two!B1",
        },
        edges=[("Two!B1", "One!AB2"), ("One!B10", "One!C2"), ("One!AA2", "One!AB2"), ("One!B2", "One!AB2")],
        literals=[Literal("One!C2", 0, 7.0)],
        sheets=["One", "Two"],
    )
    assert [c["cell"] for c in found] == ["One!B2", "One!C2", "One!AA2", "One!B10", "Two!B1"]


def test_every_constant_gets_its_own_lists():
    found = constants.find(*chain_model())
    assert len({id(c["impact"]) for c in found}) == len(found)
    assert len({id(c["outputs"]) for c in found}) == len(found)


def test_find_does_not_touch_the_graph():
    wb, graph = chain_model()
    before = {cell: set(readers) for cell, readers in graph.dependents.items()}
    constants.find(wb, graph)
    assert graph.dependents == before


# --- find_outputs ---


def test_output_is_the_rightmost_formula_cell_of_a_labelled_row():
    outputs = find_outputs(
        {
            "P&L!A3": "EBITDA",
            "P&L!B3": ("=B1-B2", 10.0),
            "P&L!C3": ("=C1-C2", 12.0),
            "P&L!D3": ("=D1-D2", 14),
            "P&L!E3": 99.0,
            "P&L!A4": "Opex",
            "P&L!B4": ("=B8+B9", 3.0),
        }
    )
    assert outputs == [{"cell": "P&L!D3", "label": "EBITDA", "value": 14.0}]
    assert isinstance(outputs[0]["value"], float)


def test_output_with_dependents_still_counts_when_the_row_is_labelled():
    outputs = find_outputs(
        {"P&L!A3": "EBITDA", "P&L!B3": ("=B1-B2", 10.0), "P&L!A4": "Check", "P&L!B4": ("=B3-10", 0.0)},
        edges=[("P&L!B3", "P&L!B4")],
    )
    assert outputs == [{"cell": "P&L!B3", "label": "EBITDA", "value": 10.0}]


@pytest.mark.parametrize(
    "label",
    [
        "EBITDA",
        "Total EBITDA",
        "ebitda (USD m)",
        "NPV",
        "Project IRR",
        "Net Income",
        "net income after tax",
        "Gross margin %",
        "Net present value",
    ],
)
def test_output_labels_match_on_word_boundaries(label):
    assert find_outputs({"S!A1": label, "S!B1": ("=B9", 1.5), "S!A2": "Other", "S!B2": ("=B8", 2.5)}) == [
        {"cell": "S!B1", "label": label, "value": 1.5}
    ]


@pytest.mark.parametrize("label", ["irrelevant", "Stirring cost", "NPVs", "EBITDAX", "Net incomes", "Gross", "Margin"])
def test_lookalike_labels_are_not_output_rows(label):
    outputs = find_outputs({"S!A1": label, "S!B1": ("=B9", 1.5), "S!A2": "EBITDA", "S!B2": ("=B8", 2.5)})
    assert [o["cell"] for o in outputs] == ["S!B2"]


def test_never_calculated_output_is_zero():
    assert find_outputs({"S!A1": "NPV", "S!B1": "=NPV(B2,B3:B9)"}) == [{"cell": "S!B1", "label": "NPV", "value": 0.0}]


def test_string_and_bool_cached_values_are_skipped():
    outputs = find_outputs(
        {
            "S!A1": "EBITDA",
            "S!B1": ("=B8-B9", 10.0),
            "S!C1": ('=IF(B1>0,"ok","check")', "ok"),
            "S!A2": "NPV",
            "S!B2": ('=TEXT(B7,"0.0")', "48.1"),
            "S!A3": "IRR",
            "S!B3": ("=B6>0", True),
            "S!A4": "Net income",
            "S!B4": ("=B5/0", "#DIV/0!"),
        }
    )
    assert outputs == [{"cell": "S!B1", "label": "EBITDA", "value": 10.0}]


def test_fallback_is_formula_cells_nothing_reads():
    outputs = find_outputs(
        {
            "S!A1": "Revenue",
            "S!B1": ("=B8*B9", 100.0),
            "S!A2": "Profit",
            "S!B2": ("=B1*0.2", 20.0),
            "S!B3": "=B1*2",
            "S!A4": "Status",
            "S!B4": ('=IF(B1>0,"ok","loss")', "ok"),
            "S!A5": "Flag",
            "S!B5": ("=B1>0", True),
            "S!A6": "Input",
            "S!B6": 7.0,
        },
        edges=[("S!B1", "S!B2"), ("S!B1", "S!B3"), ("S!B1", "S!B4"), ("S!B1", "S!B5")],
    )
    assert outputs == [
        {"cell": "S!B2", "label": "Profit", "value": 20.0},
        {"cell": "S!B3", "label": "S!B3", "value": 0.0},
    ]


def test_fallback_is_capped_at_ten():
    cells = {f"S!B{row}": (f"=A{row}*2", float(row)) for row in range(12, 0, -1)}
    outputs = find_outputs(cells)
    assert [o["cell"] for o in outputs] == [f"S!B{row}" for row in range(1, 11)]
    assert outputs[0] == {"cell": "S!B1", "label": "S!B1", "value": 1.0}


def test_no_fallback_once_any_row_matches():
    outputs = find_outputs({"S!A1": "EBITDA", "S!B1": ("=B9", 1.0), "S!A2": "Other", "S!B2": ("=B8", 2.0)})
    assert [o["cell"] for o in outputs] == ["S!B1"]


def test_no_formulas_no_outputs():
    assert find_outputs({"S!A1": "EBITDA", "S!B1": 5.0}) == []


def test_outputs_are_ordered_across_sheets():
    outputs = find_outputs(
        {
            "DCF!A2": "NPV",
            "DCF!B2": ("=B9", 48.1),
            "DCF!A1": "IRR",
            "DCF!C1": ("=B8", 0.14),
            "P&L!A10": "Net income",
            "P&L!AA10": ("=Z10", 7.0),
            "P&L!B10": ("=B9", 6.0),
            "P&L!A2": "EBITDA",
            "P&L!B2": ("=B1", 12.4),
        },
        sheets=["P&L", "DCF"],
    )
    assert [o["cell"] for o in outputs] == ["P&L!B2", "P&L!AA10", "DCF!C1", "DCF!B2"]


def test_same_row_number_on_two_sheets_gives_two_outputs():
    outputs = find_outputs(
        {"A!A1": "EBITDA", "A!B1": ("=B9", 1.0), "B!A1": "EBITDA", "B!B1": ("=B9", 2.0), "B!C1": ("=C9", 3.0)}
    )
    assert [o["cell"] for o in outputs] == ["A!B1", "B!C1"]


# --- schema ---


def test_every_constant_matches_the_schema():
    found = constants.find(*chain_model())
    assert {c["embedded"] for c in found} == {True, False}
    for constant in found:
        jsonschema.validate(constant, CONSTANT_SCHEMA)


def test_report_built_from_outputs_and_constants_matches_the_schema():
    wb, graph = chain_model()
    report = {
        "model_id": "chain",
        "filename": "chain.xlsx",
        "built_on": "2026-08-01",
        "checked_on": "2026-10-10",
        "outputs": constants.find_outputs(wb, graph),
        "constants": constants.find(wb, graph),
    }
    assert report["outputs"] == [{"cell": "P&L!B5", "label": "EBITDA", "value": 370.0}]
    jsonschema.validate(report, SCHEMA)
    json.dumps(report)
