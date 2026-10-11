"""Part 1, semantic labeling: what does this number stand for, and should it be checked?

Reads the cell's own context, the text to its right in the row (unit, note), its formula, the inputs it
is combined with, and its routes through the dependency graph to the outputs. Cheap rules first, OpenAI for the rest.
"""

import json
import re

from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.utils.cell import coordinate_from_string

from checks import graph_summary
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
events: for market only, 2 or 3 web search queries for recent events that would move this quantity (policy decisions, tariffs, supply shocks, price cuts, central bank moves); otherwise an empty list.
paths_to_outputs shows how the number flows through the model to its outputs; use it to understand what the number is.
Use only the text given. Do not guess a value."""

SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string"},
        "role": {"type": "string", "enum": list(ROLES)},
        "unit": {"type": "string"},
        "search": {"type": "array", "items": {"type": "string"}},
        "events": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["label", "role", "unit", "search", "events"],
    "additionalProperties": False,
}

_cache: dict[str, dict] = {}


def apply(constant: dict, wb, graph=None) -> None:
    """Sets label, driver, label_source, confirmed, plus additive role, search, events and graph_summary."""
    graph = graph if graph is not None else _graph(wb)
    clues = describe(constant, wb, graph)
    result = _rule(constant) or _ask(clues) or _fallback(clues)
    constant["label"] = result["label"]
    constant["role"] = result["role"]
    constant["search"] = result.get("search", []) if result["role"] in ("market", "lever") else []
    constant["events"] = result.get("events", []) if result["role"] == "market" else []
    constant["graph_summary"] = {"paths": clues.get("paths_to_outputs", []), "combined_with": clues.get("combined_with", [])}
    constant["driver"] = slug(result["label"]) if result["role"] == "market" else None
    constant["label_source"] = result["source"]
    constant["confirmed"] = False


BATCH = 20
BATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"index": {"type": "integer"}, **SCHEMA["properties"]},
                "required": ["index", *SCHEMA["required"]],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def apply_all(constants: list[dict], wb, graph=None) -> None:
    """Same as apply on every constant, with up to BATCH constants labeled per OpenAI call."""
    graph = graph if graph is not None else _graph(wb)
    todo = {}
    for c in constants:
        clues = describe(c, wb, graph)
        key = _key(clues)
        if not _rule(c) and key not in _cache:
            todo[key] = clues
    items = list(todo.items())
    for start in range(0, len(items), BATCH):
        chunk = items[start:start + BATCH]
        user = "Numbers to label. Return one item per index.\n" + json.dumps(
            [{"index": i, **_compact(clues)} for i, (_, clues) in enumerate(chunk)], indent=1, default=str)
        try:
            answer = chat_json(SYSTEM, user, BATCH_SCHEMA, "labels")
        except LLMUnavailable:
            continue
        for item in answer.get("items", []):
            i = item.pop("index", None)
            if isinstance(i, int) and 0 <= i < len(chunk):
                _cache[chunk[i][0]] = item
    for c in constants:
        apply(c, wb, graph)  # cached answers, or a single call / fallback for anything the batch missed


def describe(constant: dict, wb, graph=None) -> dict:
    """Everything the labeler sees about one constant. Raw text only."""
    cell = constant["cell"]
    anchor = (constant.get("cells") or [cell])[0]  # a literal copied across a row comes as "P&L!C18:G18"
    ctx = _context(wb, anchor)
    clues = {
        "cell": cell,
        "value": constant["value"],
        "embedded": constant.get("embedded", False),
        "formula": constant.get("formula"),
        "row_label": ctx.get("row_label"),
        "col_header": ctx.get("col_header"),
        "number_format": ctx.get("number_format"),
        "comment": ctx.get("comment"),
        "row_text_right": _text_right(wb, anchor),
    }
    if graph is not None:
        summary = graph_summary.summarize(constant, wb, graph)
        clues["combined_with"] = summary["combined_with"]
        clues["paths_to_outputs"] = graph_summary.describe_paths(summary)
    return clues


def _graph(wb):
    try:
        return graph_summary.graph_for(wb)
    except Exception:
        return None


def slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:60]


def _rule(constant: dict) -> dict | None:
    value = constant["value"]
    if constant.get("embedded") and float(value).is_integer() and abs(value) in UNIT_LITERALS:
        return {"label": f"Unit constant ({value:g})", "role": "unit", "source": "header"}
    return None


def _key(clues: dict) -> str:
    return json.dumps(clues, sort_keys=True, default=str)


def _compact(clues: dict) -> dict:
    return {k: v for k, v in clues.items() if v not in (None, [], "")}


def _ask(clues: dict) -> dict | None:
    key = _key(clues)
    if key not in _cache:
        user = "Number to label:\n" + json.dumps(_compact(clues), indent=2, default=str)
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
