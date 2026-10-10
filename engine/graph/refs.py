"""Cell keys ("Sheet!A1") and reference parsing. No dependencies on the rest of graph/."""

import re

from openpyxl.utils import column_index_from_string, get_column_letter

# (min_row, min_col, max_row, max_col), 1-based and inclusive, as openpyxl reports them
Bounds = tuple[int, int, int, int]

_COL = r"\$?[A-Za-z]{1,3}"
_ROW = r"\$?[1-9][0-9]*"
_CELL = _COL + _ROW
_REF = re.compile(
    rf"(?:(?:'(?P<quoted>(?:[^']|'')+)'|(?P<bare>[\w.]+))!)?"
    rf"(?P<coord>{_CELL}(?::{_CELL})?|{_COL}:{_COL}|{_ROW}:{_ROW})"
)
_RANGE = re.compile(r"([A-Z]{1,3})?([1-9][0-9]*)?:([A-Z]{1,3})?([1-9][0-9]*)?")
# not allowed in a sheet name, so inside quotes they mean a workbook path or a 3D reference
_NOT_IN_SHEET_NAME = set("[]:*?/\\")


def make_key(sheet: str, coord: str) -> str:
    """("Assumptions", "$c$14") -> "Assumptions!C14". Sheet name kept verbatim, never quoted."""
    return f"{sheet}!{coord.replace('$', '').upper()}"


def split_key(key: str) -> tuple[str, str]:
    """"Assumptions!C14" -> ("Assumptions", "C14"). Splits on the last "!"."""
    sheet, _, coord = key.rpartition("!")
    return sheet, coord


def parse_ref(ref: str, current_sheet: str) -> tuple[str, str] | None:
    """A reference as written in a formula -> (sheet, coord or range), $ stripped, upper case.
    None for references into another workbook or anything that is not a cell/range reference."""
    match = _REF.fullmatch(ref) if isinstance(ref, str) else None
    if match is None:
        return None
    sheet = current_sheet
    if match["quoted"] is not None:
        sheet = match["quoted"].replace("''", "'")
        if _NOT_IN_SHEET_NAME & set(sheet):
            return None
    elif match["bare"] is not None:
        sheet = match["bare"]
    return sheet, match["coord"].replace("$", "").upper()


def expand_range(sheet: str, rng: str, bounds: Bounds | None = None) -> list[str]:
    """"A1:C3" -> keys in row-major order; a single coord -> [key]. Clipped to bounds when given.
    Whole-column ("A:C") and whole-row ("1:3") ranges need bounds."""
    if ":" not in rng:
        return [make_key(sheet, rng)]
    match = _RANGE.fullmatch(rng)
    col1, row1, col2, row2 = match.groups() if match else (None,) * 4
    if (col1 is None) != (col2 is None) or (row1 is None) != (row2 is None) or not (col1 or row1):
        raise ValueError(f"not a range: {rng!r}")
    if bounds is None and (col1 is None or row1 is None):
        raise ValueError(f"whole-row/column range {rng!r} needs bounds")

    rows = _span(row1, row2, int, bounds and (bounds[0], bounds[2]))
    cols = _span(col1, col2, column_index_from_string, bounds and (bounds[1], bounds[3]))
    letters = [get_column_letter(col) for col in cols]
    return [f"{sheet}!{letter}{row}" for row in rows for letter in letters]


def ref_cells(ref: str, current_sheet: str, bounds: dict[str, Bounds]) -> list[str]:
    """parse_ref + expand_range against the workbook's sheets (the keys of bounds).
    [] for external, unparsable or unknown-sheet references."""
    parsed = parse_ref(ref, current_sheet)
    if parsed is None:
        return []
    sheet, rng = parsed
    if sheet not in bounds:
        by_lower = {name.lower(): name for name in bounds}
        sheet = by_lower.get(sheet.lower())
        if sheet is None:
            return []
    return expand_range(sheet, rng, bounds[sheet])


def _span(start: str | None, end: str | None, to_index, limits: tuple[int, int] | None) -> range:
    """Inclusive index range between two range ends on one axis, clipped to limits when given.
    Missing ends (whole-row/column ranges) span the limits."""
    if start is None or end is None:
        return range(limits[0], limits[1] + 1)
    low, high = sorted((to_index(start), to_index(end)))
    if limits is not None:
        low, high = max(low, limits[0]), min(high, limits[1])
    return range(low, high + 1)
