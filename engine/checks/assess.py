"""Part 3, LLM call: OpenAI reads the scraped pages and says whether the constant is out of date.

The model only reports what a page says (a number and the exact sentence). verify.py turns that
into the suggested value; the model never writes the suggested value itself.
"""

import json

from checks.openai_client import chat_json

SYSTEM = """You check whether a hardcoded assumption in a financial model was still accurate on a given date.
You get the assumption (label, value, unit), the date it was set (built_on), the date to check (as_of), and numbered source pages.
Use ONLY the pages. Never use your own knowledge for numbers.

Report one finding, the best-supported one, as one of:
- "level": a page states the quantity itself as of a date near as_of (e.g. "EV repairs cost about 56% more than gas cars" for a ratio of EV to gas repair cost). Give the number exactly as written and how to turn it into the model's units:
    as_is (1.56 -> 1.56), percent_to_decimal (5.63% -> 0.0563), percent_more_to_ratio (56% more -> 1.56), percent_less_to_ratio (30% less -> 0.70).
- "change": a page states how much this quantity, or the closest published measure of it, changed between built_on and as_of, in percent (e.g. "used EV prices fell 30.6% year over year" -> -30.6).
- "ratio_of_levels": a page states the closest published measure at two dates, one near built_on and one near as_of (e.g. "$91 per unit vs $55 a year earlier" -> then 55, now 91).
- "none": no page supports a number.

quotes: one or two sentences copied EXACTLY, character for character, from a single page, containing every number you report.
page: that page's id.
p_stale: your probability (0 to 1) that the model's value was materially wrong on as_of, given the pages. Use 0.5 when the pages say nothing useful."""

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
    },
    "required": ["p_stale", "kind", "number", "transform", "then", "now", "quotes", "page"],
    "additionalProperties": False,
}


def assess(constant: dict, pages: list[dict], built_on: str, as_of: str) -> dict:
    """The model's raw finding. Raises LLMUnavailable if OpenAI can't be reached."""
    if not pages:
        return {"p_stale": 0.5, "kind": "none", "number": None, "transform": None, "then": None, "now": None, "quotes": [], "page": None}
    user = json.dumps(
        {
            "assumption": {
                "label": constant["label"],
                "value": constant["value"],
                "cell": constant["cell"],
                "formula": constant.get("formula"),
            },
            "built_on": built_on,
            "as_of": as_of,
            "pages": [{k: p.get(k) for k in ("id", "publisher", "date", "title", "text")} for p in pages],
        },
        indent=1,
    )
    return chat_json(SYSTEM, user, SCHEMA, "assessment")
