"""Parse an answer key (data/ground_truth*.md) into expectations. A row the parser does not fully
understand raises TruthError naming the file and the row; nothing is guessed."""

import re
from dataclasses import dataclass
from pathlib import Path

from openpyxl.utils.cell import rows_from_range

_WORKBOOK = re.compile(r"^Workbook: `(?P<workbook>[^`]+\.xlsx)` \(assumptions set (?P<built_on>\d{4}-\d{2}-\d{2})\b", re.MULTILINE)
_SECTIONS = {"planted": "## Planted market drivers", "controls": "## Controls", "other": "## Other hardcoded inputs"}
_CHECKED_COLUMNS = ["Cell", "Driver", "Value in model", "Expected live (source, date)", "Should be stale?"]
_OTHER_COLUMNS = ["Cell", "Driver", "Value in model"]

_REF = r"[A-Z]+\d+(?::[A-Z]+\d+)?"
_CELL = re.compile(rf"(?P<sheet>[^!`(),;]+)!(?P<ref>{_REF})(?: \(buried: `(?P<formula>=[^`]+)`\))?")
_CELL_LIST = re.compile(rf"(?P<sheet>[^!`(),;]+)!(?P<refs>{_REF}(?:, {_REF})*)")
_ROW_NUMBERS = r"\d+(?:(?:, | and )\d+)*"
_ROW_GROUP = rf"[^\s,;]+ rows? {_ROW_NUMBERS}"
_ROW_LIST = re.compile(rf"{_ROW_GROUP}(?:[,;] {_ROW_GROUP})* \(buried\)")
_ROW_GROUPS = re.compile(rf"(?P<sheet>[^\s,;]+) rows? (?P<numbers>{_ROW_NUMBERS})")

_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")
_NUMBER = r"\$?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?"
_LEADING_NUMBER = re.compile(rf"(?P<number>{_NUMBER})(?![\w%]|\.\d)")
_FORMULA_LITERAL = re.compile(r"(?<![A-Za-z$\d.])\d+(?:\.\d+)?")
# an expected-live cell names a second acceptable source with one of these phrases
_ALTERNATIVE = re.compile(rf"(?:future is lower,|Market close|settled at) (?P<number>{_NUMBER}) on \d{{4}}-\d{{2}}-\d{{2}}")

_AMOUNT = r"[+-]\$[\d,]+(?:\.\d+)?M"
_KIND = r"EBITDA|net income|EV"
_KIND_NAMES = {"ebitda": "ebitda", "net income": "net_income", "ev": "ev"}  # the keys a Planted.impacts can have
_KIND_WORD = re.compile(rf"\b(?:{_KIND})\b", re.IGNORECASE)
_CLAUSE = re.compile(rf"\b(?P<kinds>(?:{_KIND})(?:(?:, | and )(?:{_KIND}))*) (?P<change>unchanged|{_AMOUNT})", re.IGNORECASE)
_DRIFT = re.compile(r"(?<![\w.$])(?P<size>[+-]\d+(?:\.\d+)?)(?P<unit>bp|pp|%)")
_SOURCE = re.compile(r"\bOn [A-Za-z][A-Za-z ]*: ")
_ON_THE_FUTURE = re.compile(rf"\((?P<amounts>{_AMOUNT}(?:(?:, | and ){_AMOUNT})*) on the future\)")
# a drift quoted to one decimal (or a whole basis point) is within half a step of the exact figure
_DRIFT_SCALE = {"bp": (10_000, 0.5), "pp": (100, 0.05), "%": (100, 0.05)}


class TruthError(ValueError):
    """An answer-key row the parser does not fully understand."""


@dataclass(frozen=True)
class Alternative:
    """A second acceptable live value. impacts is None when the key gives none for it."""

    live: float
    impacts: dict[str, float] | None = None


@dataclass(frozen=True)
class Planted:
    cell: str
    driver: str
    value: float
    live: float
    stale: bool
    impacts: dict[str, float]
    alternatives: tuple[Alternative, ...] = ()
    formula: str | None = None


@dataclass(frozen=True)
class Control:
    cell: str
    driver: str
    value: float
    live: float
    stale: bool = False
    formula: str | None = None


@dataclass(frozen=True)
class Other:
    """Inputs that are not market drivers: literal cells, and whole rows whose formulas bury unit constants."""

    driver: str
    cells: tuple[str, ...] = ()
    rows: tuple[tuple[str, int], ...] = ()


@dataclass(frozen=True)
class Truth:
    path: Path
    workbook: str
    built_on: str
    planted: tuple[Planted, ...]
    controls: tuple[Control, ...]
    other: tuple[Other, ...]

    @property
    def other_cells(self) -> list[str]:
        return [cell for entry in self.other for cell in entry.cells]

    @property
    def other_rows(self) -> list[tuple[str, int]]:
        return [row for entry in self.other for row in entry.rows]


def load(path: Path | str) -> Truth:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    header = _WORKBOOK.search(text)
    if header is None:
        raise TruthError(f"{path.name}: no 'Workbook: `name.xlsx` (assumptions set YYYY-MM-DD' line")
    rows = {name: _table(text, heading, path) for name, heading in _SECTIONS.items()}
    truth = Truth(
        path=path,
        workbook=header["workbook"],
        built_on=header["built_on"],
        planted=tuple(_each(rows["planted"], _CHECKED_COLUMNS, _planted, path, "planted")),
        controls=tuple(_each(rows["controls"], _CHECKED_COLUMNS, _control, path, "control")),
        other=tuple(_each(rows["other"], _OTHER_COLUMNS, _other, path, "other")),
    )
    cells = [row.cell for row in truth.planted + truth.controls] + truth.other_cells
    repeated = sorted({cell for cell in cells if cells.count(cell) > 1})
    if repeated:
        raise TruthError(f"{path.name}: listed more than once: {', '.join(repeated)}")
    return truth


def _table(text: str, heading: str, path: Path) -> list[list[str]]:
    """Rows of the first markdown table under a heading, the column names first."""
    sections = [section for section in re.split(r"^(?=## )", text, flags=re.MULTILINE) if section.startswith(heading)]
    if len(sections) != 1:
        raise TruthError(f"{path.name}: expected one '{heading}' section, found {len(sections)}")
    lines = [line.strip() for line in sections[0].splitlines() if line.lstrip().startswith("|")]
    if len(lines) < 3 or set(lines[1]) - set("|-: "):
        raise TruthError(f"{path.name}: no table under '{heading}'")
    return [[field.strip() for field in line.strip("|").split(" | ")] for line in lines[:1] + lines[2:]]


def _each(rows: list[list[str]], columns: list[str], parse, path: Path, section: str) -> list:
    if rows[0] != columns:
        raise TruthError(f"{path.name}: {section} table has columns {rows[0]}, expected {columns}")
    parsed = []
    for number, fields in enumerate(rows[1:], start=1):
        where = f"{path.name}: {section} row {number} ({fields[0]})"
        if len(fields) != len(columns):
            raise TruthError(f"{where}: {len(fields)} columns, expected {len(columns)}")
        try:
            parsed.append(parse(*fields))
        except TruthError as error:
            raise TruthError(f"{where}: {error}") from None
    return parsed


def _planted(cell: str, driver: str, value: str, live: str, stale: str) -> Planted:
    key, formula, model, model_percent = _model(cell, value)
    primary, percent, alternatives = _lives(live)
    if percent != model_percent or any(alt_percent != percent for _, alt_percent in alternatives):
        raise TruthError("the model and live values are not all percents or all plain numbers")
    if not re.match(r"Yes\b", stale):
        raise TruthError(f"a planted driver should be stale, but the last column starts {stale[:12]!r}")
    expectations = _expectations(stale)
    if expectations[0][0] is None:
        raise TruthError("no drift such as '+21bp' or '-2.3%' before the impacts")
    if len(expectations) > 1 and len(expectations) != 1 + len(alternatives):
        raise TruthError(f"{len(expectations) - 1} alternative impacts but {len(alternatives)} alternative live values")
    lives = [primary] + [alt for alt, _ in alternatives]
    for target, (drift, _) in zip(lives, expectations):
        _check_drift(drift, model, target)
    alt_impacts = [impacts for _, impacts in expectations[1:]] or [None] * len(alternatives)
    return Planted(
        cell=key,
        driver=driver,
        value=model,
        live=primary,
        stale=True,
        impacts=expectations[0][1],
        alternatives=tuple(Alternative(alt, impacts) for alt, impacts in zip(lives[1:], alt_impacts)),
        formula=formula,
    )


def _control(cell: str, driver: str, value: str, live: str, stale: str) -> Control:
    key, formula, model, model_percent = _model(cell, value)
    primary, percent, _ = _lives(live)
    if not re.match(r"No\b", stale):
        raise TruthError(f"a control should not be stale, but the last column starts {stale[:12]!r}")
    if percent != model_percent or not _close(primary, model):
        raise TruthError(f"a control's live value {primary:g} should equal its model value {model:g}")
    return Control(cell=key, driver=driver, value=model, live=primary, formula=formula)


def _model(cell: str, value: str) -> tuple[str, str | None, float, bool]:
    """Cell key, the formula it is buried in if any, the value in the model and whether that is a percent."""
    key, formula = _cell(cell)
    model, percent = _leading(value, "value in model")
    if formula is not None and not any(_close(float(n), model) for n in _FORMULA_LITERAL.findall(formula)):
        raise TruthError(f"value in model {model:g} is not a literal in {formula}")
    return key, formula, model, percent


def _other(cell: str, driver: str, value: str) -> Other:
    cells = _CELL_LIST.fullmatch(cell)
    if cells is not None:
        refs = cells["refs"].split(", ")
        return Other(driver=driver, cells=tuple(key for ref in refs for key in _expand(cells["sheet"], ref)))
    if _ROW_LIST.fullmatch(cell) is not None:
        groups = _ROW_GROUPS.finditer(cell)
        rows = [(group["sheet"], int(n)) for group in groups for n in re.findall(r"\d+", group["numbers"])]
        return Other(driver=driver, rows=tuple(rows))
    raise TruthError("cell is neither 'Sheet!B6:B8, B14' nor 'Sheet rows 5, 19 and 30 (buried)'")


def _cell(text: str) -> tuple[str, str | None]:
    """('P&L!C35:G35', formula or None) from 'P&L!C35:G35 (buried: `=0.0366+...`)'."""
    match = _CELL.fullmatch(text)
    if match is None:
        raise TruthError("cell is not 'Sheet!B6', 'Sheet!C35:G35' or either followed by (buried: `=formula`)")
    return _key(match["sheet"], match["ref"]), match["formula"]


def _expand(sheet: str, ref: str) -> list[str]:
    return [_key(sheet, coord) for row in rows_from_range(ref) for coord in row]


def _key(sheet: str, ref: str) -> str:
    """A cell or range the way the engine writes it: no quotes around the sheet name."""
    return sheet.strip().strip("'") + "!" + ref


def _leading(text: str, what: str) -> tuple[float, bool]:
    """The number a field opens with and whether it is a percent: '3.66% (FRED...)' -> (0.0366, True)."""
    match = _LEADING_NUMBER.match(_LINK.sub("", text))
    if match is None:
        raise TruthError(f"{what} does not open with a plain number: {text[:30]!r}")
    return _number(match["number"])


def _number(token: str) -> tuple[float, bool]:
    percent = token.endswith("%")
    number = float(token.strip("$%").replace(",", ""))
    return (round(number / 100, 12) if percent else number), percent


def _lives(text: str) -> tuple[float, bool, list[tuple[float, bool]]]:
    """Primary live value, whether it is a percent, and the alternatives named after it."""
    primary, percent = _leading(text, "expected live")
    return primary, percent, [_number(match["number"]) for match in _ALTERNATIVE.finditer(_LINK.sub("", text))]


def _expectations(text: str) -> list[tuple[tuple[float, str] | None, dict[str, float]]]:
    """(drift, impacts by output kind in $M) for the primary live value, then for each alternative.
    Every dollar amount and every output named in the prose has to be accounted for."""
    text = text.replace("\N{MINUS SIGN}", "-")
    sources = _SOURCE.split(text)
    segments = sources[1:] if len(sources) > 1 else [text]
    if len(sources) == 2:
        raise TruthError("one 'On <source>:' segment; expected none, or one per live value")
    expectations = [(_drift(segment), _impacts(segment)) for segment in segments]

    future = _ON_THE_FUTURE.search(text)
    amounts = [_amount(token) for token in re.findall(_AMOUNT, future["amounts"])] if future else []
    if future is not None:
        moved = [kind for kind, delta in expectations[0][1].items() if delta]
        if len(segments) > 1 or len(amounts) != len(moved):
            raise TruthError(f"{len(amounts)} amounts 'on the future' do not pair with the {len(moved)} outputs that move")
        expectations.append((None, expectations[0][1] | dict(zip(moved, amounts))))

    clauses = [clause for segment in segments for clause in _CLAUSE.finditer(segment)]
    named = sum(len(_KIND_WORD.findall(clause["kinds"])) for clause in clauses)
    priced = sum(clause["change"] != "unchanged" for clause in clauses) + len(amounts)
    if len(_KIND_WORD.findall(text)) != named or len(re.findall(_AMOUNT, text)) != priced:
        raise TruthError("impacts not fully understood; expected clauses like 'EBITDA unchanged, EV -$5.1M'")
    if any(not impacts for _, impacts in expectations):
        raise TruthError("no impacts such as 'EBITDA -$12.0M, EV -$137.3M'")
    return expectations


def _impacts(text: str) -> dict[str, float]:
    impacts: dict[str, float] = {}
    for clause in _CLAUSE.finditer(text):
        delta = 0.0 if clause["change"] == "unchanged" else _amount(clause["change"])
        for word in _KIND_WORD.findall(clause["kinds"]):
            kind = _KIND_NAMES[word.lower()]
            if kind in impacts:
                raise TruthError(f"two impacts for {word}")
            impacts[kind] = delta
    return impacts


def _amount(token: str) -> float:
    return float(token.replace("$", "").replace(",", "").removesuffix("M"))


def _drift(text: str) -> tuple[float, str] | None:
    match = _DRIFT.search(text)
    return (float(match["size"]), match["unit"]) if match else None


def _check_drift(drift: tuple[float, str] | None, model: float, live: float) -> None:
    """The quoted drift has to agree with the two values; a mismatch means one of them was misread."""
    if drift is None:
        return
    size, unit = drift
    if unit == "%" and not model:
        raise TruthError("a relative drift is quoted for a model value of zero")
    scale, half_step = _DRIFT_SCALE[unit]
    actual = (live / model - 1 if unit == "%" else live - model) * scale
    if abs(actual - size) > half_step + 1e-6:
        raise TruthError(f"drift {size:+g}{unit} does not match {model:g} -> {live:g} ({actual:+.2f}{unit})")


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
