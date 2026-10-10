"""Turn the LLM's finding into a check, keeping a suggested value only if the sources back it.

No network, no LLM: every rule here is plain code so it can't be talked out of.
"""

import re

STALE_REL = 0.05  # |drift| at or above 5% is stale. Tune against Driver_Map column L.
P_STALE_HIGH = 0.7
P_STALE_LOW = 0.3
MAX_RATIO = 5.0  # a suggestion more than 5x away from the model's value is a units mistake


def build_check(constant: dict, finding: dict, pages: list[dict], as_of: str) -> dict:
    """Schema-valid `check` dict for one constant."""
    value = float(constant["value"])
    page = next((p for p in pages if p.get("id") == finding.get("page")), None)
    quotes = [q for q in finding.get("quotes") or [] if q.strip()]
    backed = page is not None and quotes and all(quote_in_text(q, page["text"]) for q in quotes)

    live = None
    if backed and numbers_in_quotes(finding, quotes):
        live = suggested_value(value, finding)
        if live is not None and not plausible(value, live):
            live = None

    p_stale = _clamp(finding.get("p_stale"))
    drift_pct = round((live - value) / value * 100, 1) if live is not None and value else None
    if drift_pct is not None:
        status = "stale" if abs(drift_pct) >= STALE_REL * 100 else "current"
    elif p_stale is not None and p_stale >= P_STALE_HIGH:
        status = "stale"
    elif p_stale is not None and p_stale <= P_STALE_LOW:
        status = "current"
    else:
        status = "unknown"

    evidence = []
    if backed:
        for q in quotes:
            item = {"quote": q, "url": page["url"]}
            if page.get("publisher"):
                item["publisher"] = page["publisher"]
            if page.get("date"):
                item["date"] = page["date"]
            evidence.append(item)

    return {
        "kind": "news",
        "status": status,
        "live": live,
        "drift_pct": drift_pct,
        "p_stale": p_stale,
        "as_of": as_of,
        "source_name": page.get("publisher") if backed and live is not None else None,
        "source_url": page["url"] if backed and live is not None else None,
        "evidence": evidence,
    }


def unknown_check(as_of: str) -> dict:
    return {
        "kind": "news", "status": "unknown", "live": None, "drift_pct": None, "p_stale": None,
        "as_of": as_of, "source_name": None, "source_url": None, "evidence": [],
    }


def suggested_value(value: float, finding: dict) -> float | None:
    """The model's value restated with today's figure, in the cell's own units."""
    kind, n = finding.get("kind"), finding.get("number")
    if kind == "level" and n is not None:
        transform = finding.get("transform") or "as_is"
        if transform == "as_is":
            return float(n)
        if transform == "percent_to_decimal":
            return n / 100
        if transform == "percent_more_to_ratio":
            return 1 + n / 100
        if transform == "percent_less_to_ratio":
            return 1 - n / 100
        return None
    if kind == "change" and n is not None:
        return value * (1 + n / 100)
    if kind == "ratio_of_levels":
        then, now = finding.get("then"), finding.get("now")
        if then and now is not None:
            return value * now / then
    return None


def numbers_in_quotes(finding: dict, quotes: list[str]) -> bool:
    """Every number the model reported is written in one of its quotes."""
    kind = finding.get("kind")
    if kind in ("level", "change"):
        wanted = [finding.get("number")]
    elif kind == "ratio_of_levels":
        wanted = [finding.get("then"), finding.get("now")]
    else:
        return False
    found = [n for q in quotes for n in numbers_in(q)]
    return all(w is not None and any(_same(abs(w), f) for f in found) for w in wanted)


def numbers_in(text: str) -> list[float]:
    """Every number written in the text, ignoring sign, $ and thousands separators."""
    return [float(m.replace(",", "")) for m in re.findall(r"\d[\d,]*(?:\.\d+)?|\.\d+", text)]


def quote_in_text(quote: str, text: str) -> bool:
    return _norm(quote) in _norm(text)


def plausible(value: float, live: float) -> bool:
    if value == 0 or live == 0:
        return value == live
    ratio = abs(live / value)
    return live / value > 0 and 1 / MAX_RATIO <= ratio <= MAX_RATIO


def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


def _clamp(p) -> float | None:
    if p is None:
        return None
    return min(1.0, max(0.0, float(p)))
