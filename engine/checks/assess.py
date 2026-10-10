"""Steps 3 and 4: OpenAI compares what the constant drives (graph summary) with what the world says
(scraped figures and events), then states an updated assumption, a predicted outcome and next steps.

The model reports what pages say, with exact quotes. verify.py checks every quote, computes the
suggested value itself, and drops any sentence that uses a number no source gave.
"""

import json

from checks.openai_client import chat_json

SYSTEM = """You review one hardcoded assumption in a financial model against recent sources.

You get:
- assumption: its label, value and cell, set on built_on.
- graph: how the value flows through the model (paths from the assumption to each output it reaches) and the inputs it is combined with.
- sensitivity: the dollar impact, recalculated in the model: how much each output changes when the assumption rises from "from" to "to" (usually +10%). Deltas are in the same units as each output's value. Use it for the direction and size of every effect: if the assumption should fall, the outputs move the opposite way to the deltas.
- pages: numbered sources. kind "data" is an official series, "figure" is a published value of this quantity, "event" is news that could move it.

Use ONLY the pages for facts and numbers. Never use your own knowledge for numbers.

1. finding: the best-supported figure for this quantity as of as_of, as one of:
   - "level": a page states the quantity itself, e.g. "the WCI stood at $7,624 per 40ft container". Give the number as written and how to convert it to the model's units:
     as_is (1.56 -> 1.56), percent_to_decimal (5.63% -> 0.0563), percent_more_to_ratio (56% more -> 1.56), percent_less_to_ratio (30% less -> 0.70).
   - "change": a page states the percent change of this quantity (or its closest published measure) between built_on and as_of.
   - "ratio_of_levels": a page states the measure at two dates, near built_on (then) and near as_of (now).
   - "none": no page supports a number.
   quotes: one or two sentences copied EXACTLY from that one page, containing every number reported. page: its id.
2. events: up to 3 events from the pages that move this quantity, each with a short factual summary, the direction it pushes the quantity (raises / lowers / unclear), the page id and an exact quote.
3. effects: for each output in the sensitivity, the direction it moves if the assumption is updated to the finding (up / down / unclear). Take the direction from the sensitivity, not from the path names.
4. assumption: one sentence stating what the assumption should be now and why, citing the finding or events.
5. prediction: one sentence on what happens to the model's outputs and roughly by how much, using the sensitivity. Either quote a sensitivity delta as given ("a 10% rise lowers EBITDA by 8.5") or scale it in proportion to the change you found.
6. next_steps: 1 to 3 short imperative actions for the analyst. Name the cell and the output most affected; put the update with the largest dollar impact first. Avoid generic steps like "rerun the model" unless nothing else applies.
In assumption, prediction and next_steps use only numbers that appear in the pages, the assumption, or the sensitivity (as given or scaled to your finding).
p_stale: probability (0 to 1) that the value was materially wrong on as_of. Use 0.5 when the pages say nothing useful."""

_EVENT = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "direction": {"type": "string", "enum": ["raises", "lowers", "unclear"]},
        "page": {"type": "integer"},
        "quote": {"type": "string"},
    },
    "required": ["summary", "direction", "page", "quote"],
    "additionalProperties": False,
}

_EFFECT = {
    "type": "object",
    "properties": {
        "output": {"type": "string"},
        "direction": {"type": "string", "enum": ["up", "down", "unclear"]},
    },
    "required": ["output", "direction"],
    "additionalProperties": False,
}

SCHEMA = {
    "type": "object",
    "properties": {
        "p_stale": {"type": "number"},
        "kind": {"type": "string", "enum": ["level", "change", "ratio_of_levels", "none"]},
        "number": {"type": ["number", "null"]},
        "transform": {
            "type": ["string", "null"],
            "enum": ["as_is", "percent_to_decimal", "percent_more_to_ratio", "percent_less_to_ratio", None],
        },
        "then": {"type": ["number", "null"]},
        "now": {"type": ["number", "null"]},
        "quotes": {"type": "array", "items": {"type": "string"}},
        "page": {"type": ["integer", "null"]},
        "events": {"type": "array", "items": _EVENT},
        "effects": {"type": "array", "items": _EFFECT},
        "assumption": {"type": "string"},
        "prediction": {"type": "string"},
        "next_steps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["p_stale", "kind", "number", "transform", "then", "now", "quotes", "page",
                 "events", "effects", "assumption", "prediction", "next_steps"],
    "additionalProperties": False,
}

EMPTY = {"p_stale": 0.5, "kind": "none", "number": None, "transform": None, "then": None, "now": None,
         "quotes": [], "page": None, "events": [], "effects": [], "assumption": "", "prediction": "", "next_steps": []}


def assess(constant: dict, pages: list[dict], built_on: str, as_of: str) -> dict:
    """The model's raw finding. Raises LLMUnavailable if OpenAI can't be reached."""
    if not pages:
        return dict(EMPTY)
    summary = constant.get("graph_summary") or {}
    user = json.dumps(
        {
            "assumption": {
                "label": constant["label"],
                "value": constant["value"],
                "cell": constant["cell"],
                "formula": constant.get("formula"),
            },
            "graph": {
                "paths_to_outputs": summary.get("paths", []),
                "combined_with": summary.get("combined_with", []),
                "feeds_cells": constant.get("feeds"),
            },
            "sensitivity": constant.get("sensitivity"),
            "built_on": built_on,
            "as_of": as_of,
            "pages": [{k: p.get(k) for k in ("id", "kind", "publisher", "date", "title", "text")} for p in pages],
        },
        indent=1,
    )
    return chat_json(SYSTEM, user, SCHEMA, "assessment")
