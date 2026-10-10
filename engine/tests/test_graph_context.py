from datetime import date, datetime
from pathlib import Path

import pytest

from graph.context import context_for
from graph.parse import Workbook


def make_wb(cells: dict[str, object], sheet: str = "Assumptions", bounds=(1, 1, 20, 8), **fields) -> Workbook:
    """A one-sheet workbook from {"A1": value}; extra Workbook fields are keyed by full cell key."""
    values = {f"{sheet}!{coord}": value for coord, value in cells.items()}
    return Workbook(path=Path("x.xlsx"), sheets=[sheet], values=values, bounds={sheet: bounds}, **fields)


def assumptions_table() -> Workbook:
    return make_wb(
        {
            "A1": "Assumption",
            "B1": "FY2026",
            "A2": "EUR/USD rate",
            "B2": 1.08,
            "A3": "SOFR",
            "B3": 0.043,
        },
        formats={"Assumptions!B2": "0.00", "Assumptions!B3": "0.00%"},
    )


def test_assumptions_table():
    assert context_for(assumptions_table(), "Assumptions!B2") == {
        "sheet": "Assumptions",
        "row_label": "EUR/USD rate",
        "col_header": "FY2026",
        "number_format": "0.00",
        "comment": None,
    }


def test_exact_dict_keys():
    ctx = context_for(assumptions_table(), "Assumptions!B3")
    assert set(ctx) == {"sheet", "row_label", "col_header", "number_format", "comment"}


def test_workbook_context_method_delegates():
    wb = assumptions_table()
    assert wb.context("Assumptions!B3") == context_for(wb, "Assumptions!B3")
    assert wb.context("Assumptions!B3")["row_label"] == "SOFR"


def test_time_series_row_skips_numbers_to_reach_label():
    wb = make_wb(
        {
            "B1": "FY2024",
            "C1": "FY2025",
            "D1": "FY2026",
            "E1": "FY2027",
            "A2": "Freight cost per unit",
            "B2": 4.1,
            "C2": 4.3,
            "D2": 4.6,
            "E2": 4.9,
        }
    )
    ctx = context_for(wb, "Assumptions!D2")
    assert ctx["row_label"] == "Freight cost per unit"
    assert ctx["col_header"] == "FY2026"


def test_row_label_skips_dates_bools_and_gaps():
    wb = make_wb({"A5": "Hedge ratio", "B5": date(2026, 1, 1), "C5": True, "E5": 0.5})
    assert context_for(wb, "Assumptions!E5")["row_label"] == "Hedge ratio"


def test_nearest_text_wins():
    wb = make_wb({"A1": "Title", "A2": "Section", "B2": "Unit price", "C1": "Far", "C3": "Near", "C4": 9.5})
    wb.values["Assumptions!A4"] = "Widgets"
    wb.values["Assumptions!B4"] = "USD"
    ctx = context_for(wb, "Assumptions!C4")
    assert ctx["row_label"] == "USD"
    assert ctx["col_header"] == "Near"


def test_labels_are_stripped():
    wb = make_wb({"A2": "  Tax rate \n", "B1": "\tFY2026 ", "B2": 0.21})
    ctx = context_for(wb, "Assumptions!B2")
    assert ctx["row_label"] == "Tax rate"
    assert ctx["col_header"] == "FY2026"


def test_whitespace_only_strings_skipped():
    wb = make_wb({"A3": "Discount rate", "B3": "   ", "C3": "", "D3": 0.09, "D1": "Base case", "D2": " \n"})
    ctx = context_for(wb, "Assumptions!D3")
    assert ctx["row_label"] == "Discount rate"
    assert ctx["col_header"] == "Base case"


def test_formula_cell_with_string_cached_value_is_a_label():
    wb = make_wb(
        {"A2": "Revenue growth", "B1": "FY2026", "B2": 0.05},
        formulas={"Assumptions!A2": '="Revenue "&"growth"', "Assumptions!B1": '="FY"&2026'},
    )
    ctx = context_for(wb, "Assumptions!B2")
    assert ctx["row_label"] == "Revenue growth"
    assert ctx["col_header"] == "FY2026"


def test_numeric_year_header_fallback():
    wb = make_wb({"A2": "Volume", "B1": 2025, "C1": 2026.0, "B2": 100, "C2": 110, "B3": 120, "C3": 130})
    assert context_for(wb, "Assumptions!B3")["col_header"] == "2025"
    assert context_for(wb, "Assumptions!C3")["col_header"] == "2026"


def test_year_fallback_uses_topmost_cell_not_nearest():
    wb = make_wb({"B1": 2026, "B2": 1950, "B3": 2000, "B4": 7})
    assert context_for(wb, "Assumptions!B4")["col_header"] == "2026"


def test_year_bounds_are_inclusive():
    wb = make_wb({"A1": 1900, "B1": 2100, "C1": 1899, "D1": 2101, "A2": 1, "B2": 1, "C2": 1, "D2": 1})
    assert context_for(wb, "Assumptions!A2")["col_header"] == "1900"
    assert context_for(wb, "Assumptions!B2")["col_header"] == "2100"
    assert context_for(wb, "Assumptions!C2")["col_header"] is None
    assert context_for(wb, "Assumptions!D2")["col_header"] is None


def test_date_header_fallback():
    wb = make_wb({"B1": datetime(2026, 12, 31, 0, 0), "C1": date(2027, 6, 30), "B2": 5, "C2": 6})
    assert context_for(wb, "Assumptions!B2")["col_header"] == "2026-12-31"
    assert context_for(wb, "Assumptions!C2")["col_header"] == "2027-06-30"


def test_text_header_beats_period_above_it():
    wb = make_wb({"B1": 2026, "B2": "Actuals", "B3": 12.5})
    assert context_for(wb, "Assumptions!B3")["col_header"] == "Actuals"


def test_numeric_non_year_at_top_is_no_header():
    wb = make_wb({"B1": 1.08, "C1": 42, "D1": 2026.5, "E1": True, "B2": 2026, "B3": 3, "C2": 3, "D2": 3, "E2": 3})
    assert context_for(wb, "Assumptions!B3")["col_header"] is None
    assert context_for(wb, "Assumptions!C2")["col_header"] is None
    assert context_for(wb, "Assumptions!D2")["col_header"] is None
    assert context_for(wb, "Assumptions!E2")["col_header"] is None


def test_uncalculated_formula_at_top_is_no_header():
    wb = make_wb({"B1": None, "B2": 2026, "B3": 3}, formulas={"Assumptions!B1": "=A1+1"})
    assert context_for(wb, "Assumptions!B3")["col_header"] is None


def test_blank_string_above_a_year_does_not_hide_it():
    wb = make_wb({"B1": " ", "B2": 2026, "B3": 3})
    assert context_for(wb, "Assumptions!B3")["col_header"] == "2026"


def test_nothing_to_the_left_or_above():
    wb = make_wb({"A1": 1.08, "B2": 3, "C2": 4})
    ctx = context_for(wb, "Assumptions!A1")
    assert ctx["row_label"] is None
    assert ctx["col_header"] is None
    assert context_for(wb, "Assumptions!C2")["row_label"] is None


def test_cell_is_never_its_own_label():
    wb = make_wb({"A1": "Scenario", "B2": "Base"})
    assert context_for(wb, "Assumptions!A1")["row_label"] is None
    assert context_for(wb, "Assumptions!A1")["col_header"] is None
    assert context_for(wb, "Assumptions!B2")["row_label"] is None
    assert context_for(wb, "Assumptions!B2")["col_header"] is None


def test_text_to_the_right_or_below_is_ignored():
    wb = make_wb({"B2": 7, "C2": "units", "B3": "Notes"})
    ctx = context_for(wb, "Assumptions!B2")
    assert ctx["row_label"] is None
    assert ctx["col_header"] is None


def test_empty_cell_still_has_positional_context():
    wb = assumptions_table()
    wb.values["Assumptions!A4"] = "Freight"
    assert context_for(wb, "Assumptions!B4") == {
        "sheet": "Assumptions",
        "row_label": "Freight",
        "col_header": "FY2026",
        "number_format": "General",
        "comment": None,
    }


def test_scans_stop_at_sheet_bounds():
    wb = make_wb({"A5": "Outside", "C1": "Outside", "C5": 1}, bounds=(2, 2, 10, 6))
    ctx = context_for(wb, "Assumptions!C5")
    assert ctx["row_label"] is None
    assert ctx["col_header"] is None


def test_cell_beyond_used_area():
    wb = make_wb({"A9": "Terminal growth", "D1": "FY2030"}, bounds=(1, 1, 9, 4))
    ctx = context_for(wb, "Assumptions!XFD9")
    assert ctx["row_label"] == "Terminal growth"
    assert context_for(wb, "Assumptions!D1048576")["col_header"] == "FY2030"


def test_number_format_default_and_passthrough():
    wb = assumptions_table()
    assert context_for(wb, "Assumptions!B3")["number_format"] == "0.00%"
    assert context_for(wb, "Assumptions!A2")["number_format"] == "General"


def test_comment_stripped():
    wb = assumptions_table()
    wb.comments["Assumptions!B2"] = "  Source: ECB reference rate, Jan 2026\n"
    wb.comments["Assumptions!B3"] = " \n "
    assert context_for(wb, "Assumptions!B2")["comment"] == "Source: ECB reference rate, Jan 2026"
    assert context_for(wb, "Assumptions!B3")["comment"] is None


def test_unknown_sheet_raises_key_error():
    with pytest.raises(KeyError):
        context_for(assumptions_table(), "Inputs!B2")


def test_key_normalisation():
    wb = make_wb(
        {"A14": "EUR/USD rate", "C1": "FY2026", "B14": 1.05, "C14": 1.08},
        formats={"Assumptions!C14": "0.00"},
        comments={"Assumptions!C14": "ECB"},
    )
    expected = {
        "sheet": "Assumptions",
        "row_label": "EUR/USD rate",
        "col_header": "FY2026",
        "number_format": "0.00",
        "comment": "ECB",
    }
    assert context_for(wb, "Assumptions!$c$14") == expected
    assert context_for(wb, "Assumptions!c14") == expected
    assert context_for(wb, "Assumptions!C$14") == expected


def test_sheet_name_with_space():
    wb = make_wb(
        {"A1": "Driver", "B1": "FY2026", "A2": "SOFR", "B2": 0.043},
        sheet="Rate Inputs",
        formats={"Rate Inputs!B2": "0.00%"},
    )
    assert context_for(wb, "Rate Inputs!B2") == {
        "sheet": "Rate Inputs",
        "row_label": "SOFR",
        "col_header": "FY2026",
        "number_format": "0.00%",
        "comment": None,
    }


def test_multiple_sheets_do_not_leak():
    wb = Workbook(
        path=Path("x.xlsx"),
        sheets=["Assumptions", "Model"],
        values={"Assumptions!A2": "EUR/USD rate", "Assumptions!B1": "FY2026", "Model!B2": 10},
        bounds={"Assumptions": (1, 1, 2, 2), "Model": (1, 1, 2, 2)},
    )
    ctx = context_for(wb, "Model!B2")
    assert ctx["sheet"] == "Model"
    assert ctx["row_label"] is None
    assert ctx["col_header"] is None
