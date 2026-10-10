"""Find hardcoded constants and the model's outputs."""

import re

from openpyxl.utils import column_index_from_string
from openpyxl.utils.cell import coordinate_from_string

from graph.refs import split_key

_OUTPUT_LABEL = re.compile(r"\b(?:EBITDA|NPV|IRR|net\s+income|gross\s+margin|net\s+present\s+value)\b", re.IGNORECASE)
_PERIOD_LABEL = re.compile(r"\b(?:year|period|fiscal|FY|date)\b", re.IGNORECASE)
_MAX_FALLBACK_OUTPUTS = 10
_TRIVIAL = (0, 1, -1)

# function -> 0-based argument positions where a number is a digit count, an index or an offset, not an assumption
_STRUCTURAL_ARGS: dict[str, frozenset[int]] = {
    "ROUND": frozenset({1}),
    "ROUNDUP": frozenset({1}),
    "ROUNDDOWN": frozenset({1}),
    "TRUNC": frozenset({1}),
    "FIXED": frozenset({1}),
    "MROUND": frozenset({1}),
    "CEILING": frozenset({1}),
    "FLOOR": frozenset({1}),
    "VLOOKUP": frozenset({2, 3}),
    "HLOOKUP": frozenset({2, 3}),
    "INDEX": frozenset({1, 2}),
    "MATCH": frozenset({2}),
    "OFFSET": frozenset({1, 2, 3, 4}),
    "LEFT": frozenset({1}),
    "RIGHT": frozenset({1}),
    "MID": frozenset({1, 2}),
    "CHOOSE": frozenset({0}),
    "LARGE": frozenset({1}),
    "SMALL": frozenset({1}),
    "DATE": frozenset({0, 1, 2}),
    "EDATE": frozenset({1}),
    "EOMONTH": frozenset({1}),
    "TEXT": frozenset({1}),
    "RANK": frozenset({2}),
    "SUBTOTAL": frozenset({0}),
    "AGGREGATE": frozenset({0}),
}


def find(wb, graph) -> list[dict]:
    """Literal cells that formulas depend on, plus literals embedded in formulas.
    Each dict: cell, value, embedded, formula, feeds, outputs (see schema)."""
    sheet_index = {sheet: i for i, sheet in enumerate(wb.sheets)}
    output_cells = [output["cell"] for output in find_outputs(wb, graph)]
    found: list[tuple[tuple[int, int, int], int, dict]] = []

    for cell, value in wb.values.items():
        if cell in wb.formulas or not _is_number(value) or not graph.dependents.get(cell):
            continue
        if _is_period_header(wb, cell, value):
            continue
        reach = graph.downstream(cell)
        found.append((_position(cell, sheet_index), -1, _constant(cell, value, reach, output_cells)))

    for cell, literals in graph.literals.items():
        kept = [literal for literal in literals if not _is_structural(literal)]
        if not kept:
            continue
        reach = graph.downstream(cell) | {cell}
        position = _position(cell, sheet_index)
        formula = wb.formulas.get(cell)
        for literal in kept:
            constant = _constant(cell, literal.value, reach, output_cells, embedded=True, formula=formula)
            constant["literal_index"] = literal.index
            found.append((position, literal.index, constant))

    found.sort(key=lambda item: item[:2])
    return [constant for _, _, constant in found]


def find_outputs(wb, graph) -> list[dict]:
    """Key result cells (no dependents, or labeled EBITDA / NPV / ...). Each: cell, label, value."""
    sheet_index = {sheet: i for i, sheet in enumerate(wb.sheets)}
    candidates = sorted(
        (_position(cell, sheet_index), cell)
        for cell in wb.formulas
        if wb.values.get(cell) is None or _is_number(wb.values[cell])
    )
    rightmost: dict[tuple[int, int], str] = {}
    for (sheet, row, _), cell in candidates:
        rightmost[sheet, row] = cell

    outputs = []
    for cell in rightmost.values():
        label = wb.context(cell)["row_label"]
        if label and _OUTPUT_LABEL.search(label):
            outputs.append(_output(wb, cell, label))
    if outputs:
        return outputs

    terminal = [cell for _, cell in candidates if not graph.dependents.get(cell)]
    return [_output(wb, cell, wb.context(cell)["row_label"] or cell) for cell in terminal[:_MAX_FALLBACK_OUTPUTS]]


def _output(wb, cell: str, label: str) -> dict:
    cached = wb.values.get(cell)
    # None means the file was never calculated; the recalculation stage fills in the real value
    return {"cell": cell, "label": label, "value": 0.0 if cached is None else float(cached)}


def _constant(cell: str, value, reach: set[str], output_cells: list[str], *, embedded=False, formula=None) -> dict:
    """A constant in report shape; reach is every cell it feeds. Label and check fields are filled in later."""
    return {
        "cell": cell,
        "value": float(value),
        "embedded": embedded,
        "formula": formula,
        "label": "",
        "driver": None,
        "label_source": "header",
        "confirmed": False,
        "feeds": len(reach),
        "outputs": [output for output in output_cells if output in reach],
        "check": None,
        "impact": [],
    }


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_period_header(wb, cell: str, value: float) -> bool:
    """A year in a header row: 1900-2100 with no row label, or one that says year / period / date."""
    if not (float(value).is_integer() and 1900 <= value <= 2100):
        return False
    label = wb.context(cell)["row_label"]
    return label is None or _PERIOD_LABEL.search(label) is not None


def _is_structural(literal) -> bool:
    """0, 1 and -1, and numbers that are a function's digit count, index or offset."""
    if literal.value in _TRIVIAL:
        return True
    return literal.arg in _STRUCTURAL_ARGS.get(literal.func, ())


def _position(cell: str, sheet_index: dict[str, int]) -> tuple[int, int, int]:
    """Sort key for workbook order: sheet, then row, then column."""
    sheet, coord = split_key(cell)
    letter, row = coordinate_from_string(coord)
    return sheet_index.get(sheet, len(sheet_index)), row, column_index_from_string(letter)
