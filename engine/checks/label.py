"""Part 1, semantic labeling: what does this number stand for, and should it be checked?

Reads the cell's own context, the text to its right in the row (unit, note), its formula, and the
labels of its neighbours in the dependency graph. Cheap rules first, OpenAI for the rest.
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor

from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.utils.cell import coordinate_from_string

from checks.openai_client import LLMUnavailable, chat_json

ROLES = ("market", "lever", "internal", "unit")

# Numbers inside formulas that are almost always unit conversions, not assumptions.
UNIT_LITERALS = {7, 12, 24, 52, 60, 100, 365, 366, 1_000, 1_000_000, 1_000_000_000}

SYSTEM = """You label hardcoded numbers in financial models. You are given one number and the text around it.
Decide what real-world quantity it stands for and its role:
- market: set by the outside world and can go out of date (prices, rates, market values, industry cost ratios, fees set by third parties).
- lever: a management decision that has a market reference but is the company's choice (its own prices).
- internal: company plan, policy, headcount, fleet size, historical fact, internal cost or budget.
- unit: a unit conversion or scaling factor (days per year, months per year, thousands, millions).
label: a short, specific noun phrase naming the quantity and its unit basis, e.g. "Residual value of an EV at disposal (% of cost)".
search: for market and lever only, 2 or 3 web search queries that would find published figures for this quantity; otherwise an empty list.
Use only the text given. Do not guess a value."""

SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string"},
        "role": {"type": "string", "enum": list(ROLES)},
        "unit": {"type": "string"},
        "search": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["label", "role", "unit", "search"],
    "additionalProperties": False,
}

_cache: dict[str, dict] = {}


def apply(constant: dict, wb, graph=None) -> None:
    """Sets label, driver, label_source, confirmed, plus additive role and search."""
    clues = describe(constant, wb, graph)
    result = _rule(constant) or _ask(clues) or _fallback(clues)
    constant["label"] = result["label"]
    constant["role"] = result["role"]
    constant["search"] = result.get("search", []) if result["role"] in ("market", "lever") else []
    constant["driver"] = slug(result["label"]) if result["role"] == "market" else None
    constant["label_source"] = result["source"]
    constant["confirmed"] = False


def apply_all(constants: list[dict], wb, graph=None, workers: int = 8) -> None:
    """Same as apply on every constant, with the LLM calls run in parallel."""
    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(lambda c: apply(c, wb, graph), constants))


def describe(constant: dict, wb, graph=None) -> dict:
    """Everything the labeler sees about one constant. Raw text only."""
    cell = constant["cell"]
    ctx = _context(wb, cell)
    clues = {
        "cell": cell,
        "value": constant["value"],
        "embedded": constant.get("embedded", False),
        "formula": constant.get("formula"),
        "row_label": ctx.get("row_label"),
        "col_header": ctx.get("col_header"),
        "number_format": ctx.get("number_format"),
        "comment": ctx.get("comment"),
        "row_text_right": _text_right(wb, cell),
    }
    if graph is not None:
        precedents = getattr(graph, "precedents", {})
        dependents = getattr(graph, "dependents", {})
        if clues["embedded"]:
            # the other cells in the same formula say what the literal is multiplied with
            clues["formula_uses"] = _labels(wb, precedents.get(cell, ()))
        step1 = set(dependents.get(cell, ()))
        step2 = {d for s in step1 for d in dependents.get(s, ())} - step1
        clues["feeds_into"] = _labels(wb, step1) + _labels(wb, step2)
    return clues


def slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:60]


def _rule(constant: dict) -> dict | None:
    value = constant["value"]
    if constant.get("embedded") and float(value).is_integer() and abs(value) in UNIT_LITERALS:
        return {"label": f"Unit constant ({value:g})", "role": "unit", "source": "header"}
    return None


def _ask(clues: dict) -> dict | None:
    key = json.dumps(clues, sort_keys=True, default=str)
    if key not in _cache:
        user = "Number to label:\n" + json.dumps({k: v for k, v in clues.items() if v not in (None, [], "")}, indent=2, default=str)
        try:
            _cache[key] = chat_json(SYSTEM, user, SCHEMA, "label")
        except LLMUnavailable:
            return None
    answer = dict(_cache[key])
    if answer.get("role") not in ROLES or not answer.get("label", "").strip():
        return None
    answer["source"] = "llm"
    return answer


def _fallback(clues: dict) -> dict:
    return {"label": clues.get("row_label") or clues["cell"], "role": "internal", "source": "header"}


def _context(wb, cell: str) -> dict:
    try:
        return wb.context(cell) or {}
    except Exception:
        return {}


def _labels(wb, cells) -> list[str]:
    """Row label (with column header) of each cell, deduplicated, in sheet order."""
    out = []
    for c in sorted(cells):
        ctx = _context(wb, c)
        text = " / ".join(t for t in (ctx.get("row_label"), ctx.get("col_header")) if t)
        if text and text not in out:
            out.append(text)
    return out[:8]


def _text_right(wb, cell: str) -> list[str]:
    """Text cells to the right in the same row: usually the unit and a note."""
    values = getattr(wb, "values", {})
    try:
        sheet, coord = cell.rsplit("!", 1)
        letter, row = coordinate_from_string(coord.replace("$", ""))
    except ValueError:
        return []
    col = column_index_from_string(letter)
    bounds = getattr(wb, "bounds", {}).get(sheet)
    last = bounds[3] if bounds else col + 6
    out = []
    for c in range(col + 1, last + 1):
        v = values.get(f"{sheet}!{get_column_letter(c)}{row}")
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    return out
