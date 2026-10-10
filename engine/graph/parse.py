"""Load a workbook and build the cell dependency graph."""

import math
import re
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
from openpyxl.formula.tokenizer import Token, Tokenizer
from openpyxl.utils import column_index_from_string
from openpyxl.utils.cell import coordinate_to_tuple
from openpyxl.worksheet.formula import ArrayFormula, DataTableFormula

from graph.refs import Bounds, expand_range, make_key, parse_ref, split_key

_SHEET_ON_BOTH_ENDS = re.compile(r"((?:'(?:[^']|'')+'|[\w.]+)!)([$\w]+):\1([$\w]+)")
_RANGE = re.compile(r"([A-Z]*)([0-9]*):([A-Z]*)([0-9]*)")
_STORAGE_PREFIX = re.compile(r"^(?:_XLFN\.|_XLWS\.)+")
_NO_DATA: Bounds = (1, 1, 0, 0)


@dataclass
class Workbook:
    """Everything read from the file, keyed by "Sheet!A1"."""

    path: Path
    sheets: list[str]
    formulas: dict[str, str] = field(default_factory=dict)  # formula cells only, e.g. "=B5*1.08"
    values: dict[str, object] = field(default_factory=dict)  # literal, or Excel's cached result (None if never calculated)
    formats: dict[str, str] = field(default_factory=dict)  # Excel number format string
    comments: dict[str, str] = field(default_factory=dict)
    bounds: dict[str, Bounds] = field(default_factory=dict)  # used area per sheet
    names: dict[str, str] = field(default_factory=dict)  # defined name (upper case) -> reference text

    def context(self, cell: str) -> dict:
        from graph.context import context_for

        return context_for(self, cell)


@dataclass
class Literal:
    """A number written inside a formula."""

    cell: str  # the formula cell
    index: int  # position among the number literals in that formula, in tokenizer order
    value: float  # with a leading - and a trailing % folded in: -5 for "-5", 0.05 for "5%"
    func: str | None = None  # innermost enclosing function, upper case, e.g. "ROUND"
    arg: int | None = None  # 0-based argument position within func


@dataclass
class Graph:
    precedents: dict[str, set[str]] = field(default_factory=dict)  # cell -> cells it reads
    dependents: dict[str, set[str]] = field(default_factory=dict)  # cell -> cells that read it
    literals: dict[str, list[Literal]] = field(default_factory=dict)
    cycles: list[list[str]] = field(default_factory=list)

    def downstream(self, cell: str) -> set[str]:
        """Every cell that depends on this one, transitively. Excludes the cell itself."""
        seen: set[str] = set()
        queue = deque([cell])
        while queue:
            for dependent in self.dependents.get(queue.popleft(), ()):
                if dependent not in seen:
                    seen.add(dependent)
                    queue.append(dependent)
        seen.discard(cell)
        return seen


def load(path) -> Workbook:
    """openpyxl twice: formulas (data_only=False) and cached values (data_only=True)."""
    path = Path(path)
    formula_wb = openpyxl.load_workbook(path, data_only=False)
    value_wb = openpyxl.load_workbook(path, data_only=True)
    try:
        wb = Workbook(path=path, sheets=[ws.title for ws in formula_wb.worksheets])
        for ws, value_ws in zip(formula_wb.worksheets, value_wb.worksheets):
            _read_sheet(wb, ws, value_ws)
        for name, defined in formula_wb.defined_names.items():
            if defined.localSheetId is None and not name.startswith("_xlnm."):
                wb.names[name.upper()] = defined.attr_text
        return wb
    finally:
        formula_wb.close()
        value_wb.close()


def _read_sheet(wb: Workbook, ws, value_ws) -> None:
    """Copy one worksheet into wb; value_ws is the same sheet from the data_only workbook."""
    sheet = ws.title
    wb.bounds[sheet] = (ws.min_row, ws.min_column, ws.max_row, ws.max_column)
    cached = value_ws._cells
    # _cells holds only the cells stored in the file; iter_rows() would create every blank in the used rectangle
    for position, cell in ws._cells.items():
        value = cell.value
        if isinstance(value, DataTableFormula):
            continue
        comment = cell.comment
        if value is None and comment is None:
            continue
        key = make_key(sheet, cell.coordinate)
        if comment is not None:
            wb.comments[key] = comment.text
        if value is None:
            continue
        if cell.data_type == "f":
            wb.formulas[key] = _formula_text(value)
            cached_cell = cached.get(position)
            wb.values[key] = cached_cell.value if cached_cell is not None else None
        else:
            wb.values[key] = value
        wb.formats[key] = cell.number_format


def _formula_text(value) -> str:
    text = value.text if isinstance(value, ArrayFormula) else value
    return text if text.startswith("=") else f"={text}"


def build_graph(wb: Workbook) -> Graph:
    """Edges to the non-empty cells each formula references, the numbers written in formulas, and cycles."""
    graph = Graph()
    references = _References(wb)
    for cell, formula in wb.formulas.items():
        tokens = _tokens(formula)
        graph.precedents[cell] = references.precedents(tokens, split_key(cell)[0])
        literals = _literals(cell, tokens)
        if literals:
            graph.literals[cell] = literals
    for cell, precedents in graph.precedents.items():
        for precedent in precedents:
            graph.dependents.setdefault(precedent, set()).add(cell)
    graph.cycles = _cycles(graph.precedents)
    return graph


def _tokens(formula: str) -> list[Token]:
    """Formula tokens without whitespace. [] when the tokenizer cannot read the formula."""
    try:
        items = Tokenizer(formula).items
    except Exception:
        return []
    return [token for token in items if token.type != Token.WSPACE]


class _References:
    """Reference text as written in a formula -> the non-empty cells it covers.
    Ranges are clipped to each sheet's data rather than wb.bounds, which one styled cell can inflate."""

    def __init__(self, wb: Workbook) -> None:
        self.values = wb.values
        self.names = wb.names
        self.cells: dict[str, list[tuple[int, int, str]]] = {sheet: [] for sheet in (*wb.sheets, *wb.bounds)}
        for key in wb.values:
            sheet, coord = split_key(key)
            self.cells.setdefault(sheet, []).append((*coordinate_to_tuple(coord), key))
        self.bounds = {sheet: _data_bounds(cells) for sheet, cells in self.cells.items()}
        self.by_lower = {sheet.lower(): sheet for sheet in self.cells}
        self.ranges: dict[tuple[str, str], tuple[str, ...]] = {}
        self.named: dict[tuple[str, str], tuple[str, ...]] = {}

    def precedents(self, tokens: list[Token], sheet: str) -> set[str]:
        """Every non-empty cell the formula's references and defined names point at."""
        found: set[str] = set()
        for text in _references(tokens, self.names):
            name = text.upper()
            found.update(self._name(name, sheet) if name in self.names else self._resolve(text, sheet))
        return found

    def _name(self, name: str, sheet: str) -> tuple[str, ...]:
        """Cells a defined name refers to. Constants, errors and names nested inside it give nothing."""
        found = self.named.get((sheet, name))
        if found is None:
            value = self.names[name]
            tokens = _tokens("=" + value.lstrip("=")) if isinstance(value, str) else []
            cells = {key for text in _references(tokens) for key in self._resolve(text, sheet)}
            found = self.named[(sheet, name)] = tuple(cells)
        return found

    def _resolve(self, text: str, current_sheet: str) -> tuple[str, ...]:
        """() for external, unparsable or unknown-sheet references."""
        if text.count("!") > 1:
            match = _SHEET_ON_BOTH_ENDS.fullmatch(text)
            if match:
                text = f"{match[1]}{match[2]}:{match[3]}"
        parsed = parse_ref(text, current_sheet)
        if parsed is None:
            return ()
        sheet, rng = parsed
        if sheet not in self.cells:
            sheet = self.by_lower.get(sheet.lower())
            if sheet is None:
                return ()
        if ":" in rng:
            return self._range(sheet, rng)
        key = make_key(sheet, rng)
        return (key,) if key in self.values else ()

    def _range(self, sheet: str, rng: str) -> tuple[str, ...]:
        """Non-empty cells of a range, cached. Never costs more than one pass over the sheet's cells,
        so a value stranded at the far corner of a sheet cannot blow up a whole-column reference."""
        found = self.ranges.get((sheet, rng))
        if found is None:
            try:
                found = self._range_cells(sheet, rng)
            except ValueError:  # a row number too long for int()
                found = ()
            self.ranges[(sheet, rng)] = found
        return found

    def _range_cells(self, sheet: str, rng: str) -> tuple[str, ...]:
        bounds = self.bounds[sheet]
        min_row, min_col, max_row, max_col = bounds
        col1, row1, col2, row2 = _RANGE.fullmatch(rng).groups()
        if row1:
            low, high = sorted((int(row1), int(row2)))
            min_row, max_row = max(min_row, low), min(max_row, high)
        if col1:
            low, high = sorted((column_index_from_string(col1), column_index_from_string(col2)))
            min_col, max_col = max(min_col, low), min(max_col, high)
        cells = self.cells[sheet]
        if max(0, max_row - min_row + 1) * max(0, max_col - min_col + 1) <= len(cells):
            return tuple(key for key in expand_range(sheet, rng, bounds) if key in self.values)
        return tuple(
            key for row, col, key in cells if min_row <= row <= max_row and min_col <= col <= max_col
        )


def _data_bounds(cells: list[tuple[int, int, str]]) -> Bounds:
    """Smallest rectangle around a sheet's non-empty cells, given as (row, col, key)."""
    if not cells:
        return _NO_DATA
    rows = [row for row, _, _ in cells]
    cols = [col for _, col, _ in cells]
    return min(rows), min(cols), max(rows), max(cols)


def _references(tokens: list[Token], names: dict[str, str] | tuple = ()) -> Iterator[str]:
    """Text of each reference or defined-name operand, in order."""
    previous = None
    for token in tokens:
        if token.type == Token.OPERAND:
            if token.subtype == Token.RANGE:
                # "#REF!A1" is a reference into a deleted sheet: A1 is not a cell of the current one
                if not (previous is not None and previous.subtype == Token.ERROR and previous.value == "#REF!"):
                    yield token.value
            elif token.subtype == Token.NUMBER and token.value.upper() in names:
                # float() accepts "Inf" and "NaN", so the tokenizer calls names spelled that way numbers
                yield token.value
        elif token.type == Token.FUNC and token.subtype == Token.OPEN and ":" in token.value:
            # "A1:INDEX(" comes out as one function token
            yield token.value.rpartition(":")[0]
        previous = token


def _literals(cell: str, tokens: list[Token]) -> list[Literal]:
    """One Literal per number token, with the function and argument position it sits in."""
    literals: list[Literal] = []
    frames: list[list | None] = []  # [func, arg] per open function, None per open parenthesis or array
    index = 0
    for position, token in enumerate(tokens):
        if token.subtype == Token.OPEN:
            frames.append([_function_name(token.value), 0] if token.type == Token.FUNC else None)
        elif token.subtype == Token.CLOSE:
            if frames:
                frames.pop()
        elif token.type == Token.SEP:
            if token.subtype == Token.ARG and frames and frames[-1] is not None:
                frames[-1][1] += 1
        elif token.type == Token.OPERAND and token.subtype == Token.NUMBER:
            value = _number(tokens, position)
            if value is not None:
                func, arg = next((frame for frame in reversed(frames) if frame is not None), (None, None))
                literals.append(Literal(cell=cell, index=index, value=value, func=func, arg=arg))
            index += 1
    return literals


def _function_name(opener: str) -> str:
    """"_xlfn.XLOOKUP(" -> "XLOOKUP", "A1:INDEX(" -> "INDEX"."""
    name = opener[:-1].rpartition(":")[2].upper()
    return _STORAGE_PREFIX.sub("", name)


def _number(tokens: list[Token], position: int) -> float | None:
    """Value of the number token at position, with a prefix minus and a postfix percent applied.
    None for the non-finite values float() accepts ("Inf", "1E999"): those are not numbers in Excel."""
    value = float(tokens[position].value)
    if not math.isfinite(value):
        return None
    before = tokens[position - 1] if position else None
    after = tokens[position + 1] if position + 1 < len(tokens) else None
    if before is not None and before.type == Token.OP_PRE and before.value == "-":
        value = -value
    if after is not None and after.type == Token.OP_POST and after.value == "%":
        value /= 100
    return value


def _cycles(precedents: dict[str, set[str]]) -> list[list[str]]:
    """Circular references: strongly connected components of more than one cell, and cells that read
    themselves. Tarjan's algorithm with an explicit stack, since dependency chains run thousands deep."""
    order: dict[str, int] = {}
    low: dict[str, int] = {}
    component_stack: list[str] = []
    on_stack: set[str] = set()
    cycles: list[list[str]] = []

    def visit(cell: str) -> tuple[str, Iterator[str]]:
        order[cell] = low[cell] = len(order)
        component_stack.append(cell)
        on_stack.add(cell)
        return cell, iter(precedents[cell])

    for root in precedents:
        if root in order:
            continue
        path = [visit(root)]
        while path:
            cell, edges = path[-1]
            for precedent in edges:
                if precedent not in precedents:
                    continue
                if precedent not in order:
                    path.append(visit(precedent))
                    break
                if precedent in on_stack:
                    low[cell] = min(low[cell], order[precedent])
            else:
                path.pop()
                if path:
                    parent = path[-1][0]
                    low[parent] = min(low[parent], low[cell])
                if low[cell] == order[cell]:
                    component = []
                    while not component or component[-1] != cell:
                        component.append(component_stack.pop())
                        on_stack.discard(component[-1])
                    if len(component) > 1 or cell in precedents[cell]:
                        cycles.append(sorted(component))
    return sorted(cycles)
