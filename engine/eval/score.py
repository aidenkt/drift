"""Score an engine report (schema/constant.schema.json) against an answer key."""

import math
import re

from eval.truth import Planted, Truth

LIVE_REL_TOL = 0.02
LIVE_ABS_TOL = 0.0005  # used instead of the relative tolerance when the expected value is under SMALL
SMALL = 0.2
IMPACT_ABS_TOL = 0.15
IMPACT_REL_TOL = 0.02

_OUTPUT_LABELS = {
    "ebitda": lambda label: label == "ebitda",
    "net_income": lambda label: "net income" in label,
    "ev": lambda label: "enterprise value" in label,
}
_PNL_KINDS = ("ebitda", "net_income")
_ROW = re.compile(r"(?P<sheet>.+)!\$?[A-Z]+\$?(?P<row>\d+)")
_COUNTS = (
    "planted",
    "found",
    "stale",
    "has_live",
    "live_ok",
    "impact_checked",
    "impact_ok",
    "controls",
    "controls_found",
    "controls_ok",
    "other",
    "other_stale",
    "other_market",
    "false_positives",
)


def score(report: dict, truth: Truth) -> dict:
    """Per planted driver, control and other input, what the engine did; then totals and a headline."""
    constants = report.get("constants") or []
    outputs = output_cells(report)

    hits = [find(constants, row.cell, row.value) for row in truth.planted]
    planted = [_planted(row, hit, outputs) for row, hit in zip(truth.planted, hits)]
    taken = {id(hit) for hit in hits if hit is not None}
    free = [c for c in constants if id(c) not in taken]

    controls = [_control(row, find(free, row.cell, row.value)) for row in truth.controls]
    kinds = _kinds(truth, free)
    other = _other(truth, free, kinds)
    false_positives = [
        {"cell": c["cell"], "value": c.get("value"), "label": c.get("label"), "kind": kinds.get(id(c), "unlisted")}
        for c in free
        if _stale(c)
    ]

    totals = _totals(planted, controls, other, false_positives)
    return {
        "workbook": truth.workbook,
        "built_on": truth.built_on,
        "planted": planted,
        "controls": controls,
        "other": other,
        "false_positives": false_positives,
        "totals": totals,
        "headline": headline(totals),
    }


def output_cells(report: dict) -> dict[str, str]:
    """Output kind -> cell, by label. EBITDA and net income are the P&L sheet's when it has them."""
    cells = {}
    for kind, matches in _OUTPUT_LABELS.items():
        found = [o["cell"] for o in report.get("outputs") or [] if matches(str(o.get("label", "")).strip().lower())]
        if kind in _PNL_KINDS:
            found = [cell for cell in found if cell.startswith("P&L!")] or found
        if found:
            cells[kind] = found[0]
    return cells


def find(constants: list[dict], cell: str, value: float | None = None) -> dict | None:
    """The first constant at a truth cell, with that value when one is given."""
    return next(iter(matching(constants, cell, value)), None)


def matching(constants: list[dict], cell: str, value: float | None = None) -> list[dict]:
    """Constants at a truth cell: the same cell or range, or for a single cell a group that contains it."""
    return [
        c
        for c in constants
        if (c["cell"] == cell or (":" not in cell and cell in (c.get("cells") or ())))
        and (value is None or (_is_number(c.get("value")) and math.isclose(c["value"], value, rel_tol=1e-9, abs_tol=1e-12)))
    ]


def live_ok(live: float, expected: float) -> bool:
    tolerance = LIVE_ABS_TOL if abs(expected) < SMALL else LIVE_REL_TOL * abs(expected)
    return abs(live - expected) <= tolerance + 1e-12


def impact_ok(delta: float, expected: float) -> bool:
    return abs(delta - expected) <= max(IMPACT_ABS_TOL, IMPACT_REL_TOL * abs(expected)) + 1e-12


def headline(totals: dict) -> str:
    n = totals["planted"]
    stale_controls = totals["controls"] - totals["controls_ok"]
    return (
        f"planted {totals['found']}/{n} found, {totals['stale']}/{n} stale, {totals['live_ok']}/{n} live ok, "
        f"{totals['impact_ok']}/{totals['impact_checked']} impact ok; "
        f"controls {totals['controls_ok']}/{totals['controls']} ok; {totals['false_positives']} false positives"
        + (f" (controls: {stale_controls})" if stale_controls else "")
    )


def add_totals(totals: list[dict]) -> dict:
    """Totals over several cases, with the rates recomputed."""
    counts = {key: sum(t[key] for t in totals) for key in _COUNTS}
    return counts | _rates(counts)


def _planted(row: Planted, constant: dict | None, outputs: dict[str, str]) -> dict:
    live = _live(constant)
    options = [("primary", row.live, row.impacts)] + [("alternative", alt.live, alt.impacts) for alt in row.alternatives]
    close = [option for option in options if live is not None and live_ok(live, option[1])]
    matched = min(close, key=lambda option: abs(live - option[1]), default=None)
    impacts = _impacts(row, constant, live, matched, outputs) if matched else []
    return {
        "cell": row.cell,
        "driver": row.driver,
        "value": row.value,
        "expected_live": row.live,
        "alternatives": [alt.live for alt in row.alternatives],
        "found": constant is not None,
        "stale": _stale(constant),
        "has_live": live is not None,
        "live": live,
        "live_ok": matched is not None,
        "matched": matched[0] if matched else None,
        # None when the live value is off: the key's impacts are for another value and cannot be compared
        "impact_ok": all(i["ok"] for i in impacts) if impacts else None,
        "impacts": impacts,
        "engine": _engine(constant),
    }


def _impacts(row: Planted, constant: dict, live: float, matched: tuple, outputs: dict[str, str]) -> list[dict]:
    """Expected against returned change per output kind. The key's figure is for the key's live value,
    so it is scaled to the engine's by the size of the move (first order; exact when the two are equal).
    An alternative the key gives no impacts for is scaled from the primary's. An output the engine lists
    no change for moved by 0."""
    _, reference, expected = matched if matched[2] is not None else ("primary", row.live, row.impacts)
    scale = (live - row.value) / (reference - row.value) if reference != row.value else 1.0
    moved = {i["output"]: i["delta"] for i in constant.get("impact") or []}
    rows = []
    for kind, quoted in expected.items():
        cell = outputs.get(kind)
        delta = moved.get(cell, 0.0) if cell else None
        want = quoted * scale
        ok = delta is not None and impact_ok(delta, want)
        rows.append({"kind": kind, "output": cell, "expected": quoted, "expected_at_live": want, "delta": delta, "ok": ok})
    return rows


def _control(row, constant: dict | None) -> dict:
    return {
        "cell": row.cell,
        "driver": row.driver,
        "value": row.value,
        "found": constant is not None,
        "stale": _stale(constant),
        "ok": not _stale(constant),
        "engine": _engine(constant),
    }


def _kinds(truth: Truth, constants: list[dict]) -> dict[int, str]:
    """id(constant) -> 'control' or 'other' for the constants the answer key lists as not to be flagged."""
    kinds: dict[int, str] = {}
    for row in truth.controls:
        for c in matching(constants, row.cell, row.value):
            kinds.setdefault(id(c), "control")
    rows = set(truth.other_rows)
    for c in constants:
        if any(matching([c], cell) for cell in truth.other_cells) or rows & _rows(c):
            kinds.setdefault(id(c), "other")
    return kinds


def _other(truth: Truth, constants: list[dict], kinds: dict[int, str]) -> list[dict]:
    """One row per listed cell, then one per constant found in a listed row of buried unit constants."""
    listed = [(cell, [c for c in matching(constants, cell) if kinds.get(id(c)) == "other"]) for cell in truth.other_cells]
    seen = {id(c) for _, hits in listed for c in hits}
    buried = [(c["cell"], [c]) for c in constants if kinds.get(id(c)) == "other" and id(c) not in seen]
    return [
        {
            "cell": cell,
            "found": bool(hits),
            "stale": any(_stale(c) for c in hits),
            "market": any(c.get("role") == "market" for c in hits),
            "value": hits[0].get("value") if hits else None,
            "label": hits[0].get("label") if hits else None,
        }
        for cell, hits in listed + buried
    ]


def _rows(constant: dict) -> set[tuple[str, int]]:
    """(sheet, row) of every cell a constant sits in."""
    rows = set()
    for cell in constant.get("cells") or constant["cell"].split(":")[:1]:
        match = _ROW.fullmatch(cell)
        if match:
            rows.add((match["sheet"], int(match["row"])))
    return rows


def _totals(planted: list[dict], controls: list[dict], other: list[dict], false_positives: list[dict]) -> dict:
    counts = {
        "planted": len(planted),
        "found": sum(p["found"] for p in planted),
        "stale": sum(p["stale"] for p in planted),
        "has_live": sum(p["has_live"] for p in planted),
        "live_ok": sum(p["live_ok"] for p in planted),
        "impact_checked": sum(p["impact_ok"] is not None for p in planted),
        "impact_ok": sum(p["impact_ok"] is True for p in planted),
        "controls": len(controls),
        "controls_found": sum(c["found"] for c in controls),
        "controls_ok": sum(c["ok"] for c in controls),
        "other": len(other),
        "other_stale": sum(o["stale"] for o in other),
        "other_market": sum(o["market"] for o in other),
        "false_positives": len(false_positives),
    }
    return counts | _rates(counts)


def _rates(counts: dict) -> dict:
    return {
        "recall": _ratio(counts["stale"], counts["planted"]),
        "live_accuracy": _ratio(counts["live_ok"], counts["planted"]),
        "impact_accuracy": _ratio(counts["impact_ok"], counts["impact_checked"]),
    }


def _ratio(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def _engine(constant: dict | None) -> dict | None:
    """What the engine returned for a constant, trimmed to what a scorecard needs."""
    if constant is None:
        return None
    check = constant.get("check") or {}
    return {
        "cell": constant["cell"],
        "value": constant.get("value"),
        "label": constant.get("label"),
        "role": constant.get("role"),
        "driver": constant.get("driver"),
        "status": check.get("status"),
        "live": check.get("live"),
        "drift_pct": check.get("drift_pct"),
        "impact": {i["output"]: i["delta"] for i in constant.get("impact") or []},
    }


def _stale(constant: dict | None) -> bool:
    return bool(constant) and (constant.get("check") or {}).get("status") == "stale"


def _live(constant: dict | None) -> float | None:
    live = (constant.get("check") or {}).get("live") if constant else None
    return float(live) if _is_number(live) else None


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
