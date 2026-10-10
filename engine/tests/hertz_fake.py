"""A slice of the Hertz case-study workbook, shaped like graph's Workbook and Graph, for checks tests."""

from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.utils.cell import coordinate_from_string

VALUES = {
    "Inputs!A4": "Assumption", "Inputs!B4": "Value", "Inputs!C4": "Unit", "Inputs!D4": "Note",
    "Inputs!A8": "Revenue per day (RPD)", "Inputs!B8": 61, "Inputs!C8": "$ / day",
    "Inputs!D8": "Management pricing lever. Hertz reported $58.09 in Q4 2023.",
    "Inputs!A11": "EV residual value at disposal", "Inputs!B11": 0.72, "Inputs!C11": "% of cost",
    "Inputs!D11": "KEY ASSUMPTION. Set when Model 3s were reported to hold about 90% of value at three years (Electrek).",
    "Inputs!A17": "ICE collision and damage cost per rental day", "Inputs!B17": 3.4, "Inputs!C17": "$ / day",
    "Inputs!D17": "Internal (mock).",
    "Fleet_Model!A4": "Line item", "Fleet_Model!B4": "EV", "Fleet_Model!C4": "ICE",
    "Fleet_Model!A6": "Rental days",
    "Fleet_Model!A11": "Collision and damage ($M)",
    "Fleet_Model!A14": "Segment contribution ($M)",
    "Fleet_Model!A16": "Adjusted Corporate EBITDA ($M)",
}
FORMULAS = {
    "Fleet_Model!B6": "=B5*365*Inputs!$B$7",
    "Fleet_Model!B11": "=B6*Inputs!$B$17*1.2/1000000",
    "Fleet_Model!B14": "=B7-B9-B10-B11-B12-B13",
    "Fleet_Model!D16": "=D14-D15",
}
BOUNDS = {"Inputs": (1, 1, 19, 4), "Fleet_Model": (1, 1, 17, 4)}


class Workbook:
    values = VALUES
    formulas = FORMULAS
    bounds = BOUNDS

    def context(self, cell):
        sheet, coord = cell.split("!")
        letter, row = coordinate_from_string(coord)
        col = column_index_from_string(letter)
        row_label = next((self._text(sheet, c, row) for c in range(col - 1, 0, -1) if self._text(sheet, c, row)), None)
        col_header = next((self._text(sheet, col, r) for r in range(row - 1, 0, -1) if self._text(sheet, col, r)), None)
        return {"sheet": sheet, "row_label": row_label, "col_header": col_header, "number_format": "General", "comment": None}

    def _text(self, sheet, col, row):
        v = VALUES.get(f"{sheet}!{get_column_letter(col)}{row}")
        return v if isinstance(v, str) else None


class Graph:
    precedents = {
        "Fleet_Model!B11": {"Fleet_Model!B6", "Inputs!B17"},
    }
    dependents = {
        "Inputs!B17": {"Fleet_Model!B11", "Fleet_Model!C11"},
        "Inputs!B11": {"Fleet_Model!B8", "Fleet_Model!B13"},
        "Fleet_Model!B11": {"Fleet_Model!B14"},
        "Fleet_Model!B14": {"Fleet_Model!D14"},
    }


def constant(cell, value, embedded=False, formula=None):
    """Constant as graph hands it over, with checks fields at their neutral defaults."""
    return {
        "cell": cell, "value": value, "embedded": embedded, "formula": formula,
        "label": "", "driver": None, "label_source": "header", "confirmed": False,
        "feeds": 1, "outputs": [], "check": None, "impact": [],
    }
