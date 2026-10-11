"""Turn the LLM's finding into a check, keeping a suggested value only if the sources back it.

No network, no LLM: every rule here is plain code so it can't be talked out of.
"""

import logging
import math
import re

from checks.drivers import series_scale

log = logging.getLogger(__name__)

STALE_REL = 0.02  # prices, FX, ratios: a move of 2% or more is stale (EUR/USD moved 2.3% in the case study)
STALE_ABS_RATE = 0.001  # rates and percentages: a move of 0.10pp or more is stale (SOFR moved 0.21pp)
APPROX = 0.15  # an estimate scaled from the sensitivity may be rounded by up to 15%
P_STALE_HIGH = 0.7
P_STALE_LOW = 0.3
MAX_RATIO = 5.0  # a suggestion more than 5x away from the model's value is a units mistake
STALE_ABS_FROM_ZERO = 0.0025  # a model value of 0 (e.g. a 0% tariff) is stale once the source moves 0.25pp
MIN_FRAGMENT = 15  # a piece of a quote this long must be on the page; shorter ones only if they hold a digit
ROUNDING = 0.051  # two quoted levels are behind a quoted "-2.3%" if they give it to the rounding of one decimal


def build_check(constant: dict, finding: dict, pages: list[dict], as_of: str, built_on: str | None = None) -> dict:
    """Schema-valid `check` dict for one constant. With built_on, a page dated before it cannot make the
    value stale: it says what was already known when the value was set."""
    value = float(constant["value"])
    cell = constant.get("cell")
    page = next((p for p in pages if p.get("id") == finding.get("page")), None)
    said = [_unmangle(q) for q in finding.get("quotes") or [] if q.strip()]
    quotes = [q for q in said if page is not None and quote_in_text(q, _text(page))]  # the rest are never used
    backed = bool(quotes)
    if page is not None and len(quotes) < len(said):
        log.info("%s: quote not on page %s: %r", cell, page["id"], [q for q in said if q not in quotes][:1])

    live, source = None, None  # source: the page live was read from
    fred = fred_live(constant, pages)
    if fred:
        live, source = fred  # whatever the finding says: it still supplies the events and the sentences
        log.info("%s: %s read from %s itself, not from the LLM", cell, live, source.get("title"))
    elif finding.get("kind") in (None, "none"):
        log.info("%s: no figure found in the sources", cell)
    elif page is None:
        log.info("%s: suggestion dropped, page %s does not exist", cell, finding.get("page"))
    elif not backed:
        log.info("%s: suggestion dropped, no quote is on page %s", cell, finding.get("page"))
    elif not numbers_in_quotes(finding, quotes):
        log.info("%s: suggestion dropped, number %s not in quote %r", cell, finding.get("number"), quotes[:1])
    else:
        live, source = suggested_value(value, finding, quotes), page
        if live is not None and not plausible(value, live, finding):
            log.info("%s: suggestion dropped, %s is implausible next to %s (units?)", cell, live, value)
            live = None
        elif live is not None and predates(page, built_on) and moved(constant, value, live):
            log.info("%s: suggestion dropped, %s is from a page dated %s, before the model", cell, live, page["date"])
            live = None

    cited = [(source["text"], source)] if fred else []
    cited += [(q, page) for q in quotes if not (fred and page is source)]  # the FRED page is cited whole, once
    evidence = []
    for q, p in cited:
        item = {"quote": q, "url": p["url"]}
        if p.get("publisher"):
            item["publisher"] = p["publisher"]
        if p.get("date"):
            item["date"] = p["date"]
        evidence.append(item)
    events = verified_events(finding, pages)

    p_stale = _clamp(finding.get("p_stale"))
    drift_pct = round((live - value) / value * 100, 1) if live is not None and value else None
    if live is not None:
        status = "stale" if moved(constant, value, live) else "current"
    else:
        recent = [p["url"] for p in pages if since(p, built_on)]
        figure = backed and finding.get("kind") not in (None, "none") and page["url"] in recent
        pushed = any(e["direction"] in ("raises", "lowers") and e["url"] in recent for e in events)
        status = unverified_status(constant, value, finding, p_stale, bool(evidence or events), figure or pushed)

    sens = constant.get("sensitivity")
    exact, scaled = sensitivity_numbers(sens, live)
    allowed = allowed_numbers(value, live, drift_pct, pages) + exact
    steps = [step for step in finding.get("next_steps") or [] if uses_only(step, allowed, scaled, cell)][:3]

    return {
        "kind": "news",
        "status": status,
        "live": live,
        "drift_pct": drift_pct,
        "p_stale": p_stale,
        "as_of": as_of,
        "source_name": source.get("publisher") if live is not None else None,
        "source_url": source["url"] if live is not None else None,
        "evidence": evidence,
        # additive: the comparison of graph's sensitivity and sources (steps 3 and 4)
        "events": events,
        "effects": effects_from_sensitivity(sens, value, live),
        "assumption": _sentence(finding.get("assumption"), allowed, scaled, cell),
        "prediction": _sentence(finding.get("prediction"), allowed, scaled, cell),
        "next_steps": steps,
    }


def fred_live(constant: dict, pages: list[dict]) -> tuple[float, dict] | None:
    """(live, page) read straight off a FRED observation, in the model's units, when drivers.series_scale says
    the series is this constant's own quantity and it has printed since built_on. A margin over SOFR, or a
    cell holding SOFR plus a margin, is not SOFR: those are left to the finding."""
    value = float(constant["value"])
    for page in pages:
        obs = page.get("fred")
        scale = series_scale(constant.get("label") or "", value, obs) if obs else None
        if scale is not None and obs["now_date"] > obs["then_date"]:
            live = round(obs["now"] * scale, 10)
            return (live, page) if plausible(value, live) else None
    return None


def moved(constant: dict, value: float, live: float) -> bool:
    """live is past the staleness threshold for this kind of number."""
    if is_rate(constant):
        return abs(live - value) >= STALE_ABS_RATE
    if value:
        return abs(round((live - value) / value * 100, 1)) >= STALE_REL * 100
    return abs(live) >= STALE_ABS_FROM_ZERO  # model value is 0, so no percent drift


def unverified_status(constant: dict, value: float, finding: dict, p_stale: float | None, quoted: bool,
                      supported: bool) -> str:
    """Status when no number survived verification. The LLM's confidence alone decides nothing: "stale" needs
    support (a verified quote for a figure it reported, or a verified event that raises or lowers the quantity,
    on a page dated since the model was built) and "current" needs any verified quote. Its own unverified figure
    can only hold a flag back: a finding that reads 12.5% for a 12.5% tariff is not stale, whatever p_stale says."""
    if p_stale is None:
        return "unknown"
    claimed = suggested_value(value, finding)
    unchanged = claimed is not None and not moved(constant, value, claimed)
    if p_stale >= P_STALE_HIGH and supported and not unchanged:
        return "stale"
    if p_stale <= P_STALE_LOW and quoted:
        return "current"
    return "unknown"


def predates(page: dict, built_on: str | None) -> bool:
    """The page is dated before the model was built, so a number on it is not news. Undated pages are not held
    to this: most pages with a figure carry no date."""
    return bool(built_on and page.get("date") and page["date"] < built_on)


def since(page: dict, built_on: str | None) -> bool:
    """The page is known to be dated since the model was built: what a flag with no number behind it needs.
    Without built_on (callers that don't pass it) every page counts."""
    return not built_on or bool(page.get("date") and page["date"] >= built_on)


def sensitivity_numbers(sens: dict | None, live: float | None) -> tuple[list[float], list[float]]:
    """(exact, scaled): figures from graph's sensitivity (bump, and each output's and path step's baseline,
    delta and pct), and the deltas scaled to the verified live value, which an estimate may round."""
    bump = (sens or {}).get("bump")
    if not bump:
        return [], []
    exact = [bump["from"], bump["to"], bump["size"] * 100]
    scaled = []
    step = bump["to"] - bump["from"]
    scale = (live - bump["from"]) / step if live is not None and step else None
    for effect in sens.get("effects") or []:
        for item in [effect, *(effect.get("path") or [])]:
            exact += [n for n in (item.get("baseline"), item.get("delta"), item.get("pct")) if n is not None]
            if scale is not None:
                scaled += [item[k] * scale for k in ("delta", "pct") if item.get(k) is not None]
    return exact, scaled


def is_rate(constant: dict) -> bool:
    """A rate or percentage held as a decimal (0.0475 for 4.75%): staleness is judged in points, not percent."""
    value = abs(float(constant.get("value") or 0))
    return value < 1 and bool(re.search(r"%|rate|yield|spread|margin|premium|tariff|duty|tax", constant.get("label") or "", re.I))


def effects_from_sensitivity(sens: dict | None, value: float, live: float | None) -> list[dict]:
    """Direction of each output when the constant moves to live, from graph's recalculated sensitivity
    (measured for a rise). [] without a live value; "unclear" where the model couldn't be recalculated."""
    if not sens or live is None or live == value:
        return []
    up = live > value
    out = []
    for effect in sens.get("effects") or []:
        moved = effect.get("direction")
        if moved in ("rises", "falls"):
            direction = "up" if (moved == "rises") == up else "down"
        else:
            direction = "unclear"
        out.append({"output": effect.get("label") or effect["output"], "direction": direction})
    return out


def verified_events(finding: dict, pages: list[dict]) -> list[dict]:
    """Events whose quote is really on the page they cite."""
    by_id = {p.get("id"): p for p in pages}
    out = []
    for e in finding.get("events") or []:
        page = by_id.get(e.get("page"))
        quote = _unmangle(e.get("quote") or "").strip()
        if page and quote and quote_in_text(quote, _text(page)):
            item = {"summary": e.get("summary", ""), "direction": e.get("direction", "unclear"),
                    "quote": quote, "url": page["url"]}
            if page.get("publisher"):
                item["publisher"] = page["publisher"]
            if page.get("date"):
                item["date"] = page["date"]
            out.append(item)
    return out[:3]


def allowed_numbers(value: float, live: float | None, drift_pct: float | None, pages: list[dict]) -> list[float]:
    """Numbers a sentence may use: the model's value, the verified suggestion and drift, and anything a source page says."""
    nums = [value, value * 100]
    if live is not None:
        nums += [live, live * 100]
    if drift_pct is not None:
        nums.append(drift_pct)
    for p in pages:
        nums += numbers_in(p.get("text", "")) + numbers_in(p.get("date") or "")
    return nums


def uses_only(text: str, allowed: list[float], scaled: list[float] = (), cell: str | None = None) -> bool:
    """True if every number in the text (ignoring cell references like B20) matches an allowed number to 1%,
    or an estimate scaled from the sensitivity to APPROX."""
    text = re.sub(r"(?:[A-Za-z_&']+!)?\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?", " ", text or "")
    for n in numbers_in(text):
        if not any(_close(n, a) for a in allowed) and not any(_close(n, a, APPROX) for a in scaled):
            log.info("%s: sentence dropped, %g is not in any source or the sensitivity", cell, n)
            return False
    return True


def _sentence(text: str | None, allowed: list[float], scaled: list[float] = (), cell: str | None = None) -> str | None:
    text = (text or "").strip()
    return text if text and uses_only(text, allowed, scaled, cell) else None


def _close(a: float, b: float, tol: float = 0.01) -> bool:
    return abs(a - abs(b)) <= tol * max(abs(a), abs(b)) + 1e-9


def unknown_check(as_of: str) -> dict:
    return {
        "kind": "news", "status": "unknown", "live": None, "drift_pct": None, "p_stale": None,
        "as_of": as_of, "source_name": None, "source_url": None, "evidence": [],
        "events": [], "effects": [], "assumption": None, "prediction": None, "next_steps": [],
    }


def suggested_value(value: float, finding: dict, quotes: list[str] | None = None) -> float | None:
    """The model's value restated with today's figure, in the cell's own units. Given the quotes, every number
    is taken as the quote writes it, not as the LLM reports it (see as_written)."""
    kind, n = finding.get("kind"), finding.get("number")
    if kind == "level" and n is not None:
        n, converted = _read(n, quotes)
        if n is None:
            return None
        if converted:  # the LLM did the units itself (0.0522 for "5.22%"): redo them here from what is written
            return _in_model_units(abs(n), value, abs(finding["number"]))
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
        written, converted = _read(n, quotes)
        if written is None:
            return None
        if converted:  # -0.023 for a quoted "-2.3%": a change is applied as a percent
            n = math.copysign(max(abs(written), abs(n)), n)
        then_now = levels_behind(n, quotes or [])
        if then_now:  # the quote also gives both levels: use them, they are not rounded
            return value * then_now[1] / then_now[0]
        return value * (1 + n / 100)
    if kind == "ratio_of_levels":
        then, now = (_read(finding.get(k), quotes)[0] for k in ("then", "now"))
        if then and now is not None:
            return value * now / then
    return None


def _read(n: float | None, quotes: list[str] | None) -> tuple[float | None, bool]:
    """as_written, or the number as reported when there are no quotes to read it from. Keeps the sign."""
    if n is None or quotes is None:
        return n, False
    written, converted = as_written(n, quotes) or (None, False)
    return (None if written is None else math.copysign(written, n)), converted


def _in_model_units(written: float, value: float, reported: float) -> float:
    """written, a hundredth of it or a hundred times it, whichever is nearest the model's value in magnitude:
    5.22 next to 0.0475 is 0.0522. A model value of 0 has no magnitude, so the LLM's choice of units stands."""
    options = [written, round(written / 100, 10), round(written * 100, 10)]
    if not value or not written:
        return min(options, key=lambda o: abs(o - reported))
    return min(options, key=lambda o: abs(math.log(o / abs(value))))


def as_written(n: float, quotes: list[str]) -> tuple[float, bool] | None:
    """(the number as a quote writes it, whether the LLM changed its units): (5.22, True) for a reported
    0.0522 against "5.22%". None when the quotes hold neither n nor its percent/decimal counterpart."""
    n = abs(n)
    found = [f for q in quotes for f in numbers_in(q)]
    if any(_same(n, f) for f in found):
        return n, False
    for f in (f for q in quotes for f in percents_in(q)):
        if _same(n * 100, f):  # reported as a decimal, written as a percent
            return f, True
    for f in found:
        if _same(n / 100, f):  # reported as a percent, written as a decimal
            return f, True
    return None


def levels_behind(pct: float, quotes: list[str]) -> tuple[float, float] | None:
    """(then, now) when a quote that states a change also states the two levels it was computed from:
    1.1519 and 1.1259 next to "-2.3%". Any pair found gives the stated change to its rounding, so a chance
    pair (two years, say) cannot move the result by more than that."""
    found = [f for q in quotes for f in numbers_in(q) if f]
    for then in found:
        for now in found:
            if now != then and abs((now - then) / then * 100 - pct) <= ROUNDING:
                return then, now
    return None


def numbers_in_quotes(finding: dict, quotes: list[str]) -> bool:
    """Every number the model reported is written in one of its quotes, as reported or as its percent/decimal
    counterpart (0.21 for "21%"). A number the quotes do not hold either way is never accepted."""
    kind = finding.get("kind")
    if kind in ("level", "change"):
        wanted = [finding.get("number")]
    elif kind == "ratio_of_levels":
        wanted = [finding.get("then"), finding.get("now")]
    else:
        return False
    return all(w is not None and as_written(w, quotes) is not None for w in wanted)


def numbers_in(text: str) -> list[float]:
    """Every number written in the text, ignoring sign, $ and thousands separators."""
    return [float(m.replace(",", "")) for m in re.findall(r"\d[\d,]*(?:\.\d+)?|\.\d+", text)]


def percents_in(text: str) -> list[float]:
    """The numbers written as a percent: 5.22 in "5.22%" or "5.22 percent"."""
    return [float(m.replace(",", "")) for m in re.findall(r"(\d[\d,]*(?:\.\d+)?|\.\d+)\s?(?:%|per ?cent)", text)]


def quote_in_text(quote: str, text: str) -> bool:
    """The quote is on the page: whole, or in pieces when the LLM joined lines or passages (a heading and a
    sentence, "..." between two sentences). Every piece of MIN_FRAGMENT characters or more, and any piece
    holding a digit, must be on the page; one piece that is not there fails the quote."""
    text, whole = _norm(text), _norm(quote)
    if not whole:
        return False
    if whole in text:
        return True
    parts = [p for p in map(_norm, re.split(r"\n|\.{3,}|\u2026", quote)) if p]
    checked = [p for p in parts if len(p) >= MIN_FRAGMENT or re.search(r"\d", p)]
    return any(len(p) >= MIN_FRAGMENT for p in parts) and all(p in text for p in checked)


def _text(page: dict) -> str:
    """What a quote may be copied from: the LLM is shown the title next to the text and sometimes quotes it."""
    return f"{page.get('title') or ''}\n{page['text']}"


def plausible(value: float, live: float, finding: dict | None = None) -> bool:
    if value == 0:
        # nothing to compare a ratio against: accept a stated level that reads like a rate (0–100%)
        return (finding or {}).get("kind") == "level" and 0 <= live <= 1
    if live == 0:
        return False
    ratio = abs(live / value)
    return live / value > 0 and 1 / MAX_RATIO <= ratio <= MAX_RATIO


def _norm(s: str) -> str:
    """Lowercase, with whitespace, typographic quotes, dashes and ellipses, and footnote marks ("[2]") evened out."""
    s = re.sub(r"\[\d+\]", "", s.translate(_PLAIN).replace("\u2026", "..."))
    return re.sub(r"\s+", " ", s).strip().lower()


# curly single quotes and primes, curly double quotes, hyphens and dashes
_PLAIN = str.maketrans("\u2018\u2019\u201a\u2032\u201c\u201d\u201e\u2033\u2010\u2011\u2012\u2013\u2014\u2212",
                       "''''" + '""""' + "------")


def _unmangle(s: str) -> str:
    """The LLM sometimes writes a curly quote or dash as a control character (U+201C as \\u001c): put it back."""
    return s.translate(_MANGLED)


_MANGLED = {low: 0x2000 + low for low in (0x13, 0x14, 0x18, 0x19, 0x1C, 0x1D)}


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


def _clamp(p) -> float | None:
    if p is None:
        return None
    return min(1.0, max(0.0, float(p)))
