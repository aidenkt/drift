"""Scores as plain text for a terminal."""

from eval import score

_DRIVER_WIDTH = 34
_KIND_LABELS = {"ebitda": "EBITDA", "net_income": "net income", "ev": "EV"}


def scorecard(case: str, result: dict, graph_only: bool = False) -> str:
    """One case: a line per planted driver and control, then what else was flagged, then the headline."""
    seconds = f"  {result['seconds']:.0f}s" if "seconds" in result else ""
    if "error" in result:
        detail = result.get("traceback") or result["error"]
        return "\n".join([f"{case}  FAILED{seconds}"] + _indent(detail.rstrip().split("\n")))
    scores = result["scores"]
    lines = [f"{case}  {scores['workbook']}  assumptions set {scores['built_on']}{seconds}"]
    lines += _indent(_planted(scores["planted"], graph_only))
    if graph_only:
        totals = scores["totals"]
        lines.append(f"  controls found {totals['controls_found']}/{totals['controls']}")
    else:
        lines += _indent(_controls(scores["controls"]))
        lines.append("  " + _other(scores["other"]))
        lines += _indent(_false_positives(scores["false_positives"]))
    lines.append(f"  => {_headline(scores['totals'], graph_only)}")
    return "\n".join(lines)


def overall(results: dict[str, dict], graph_only: bool = False) -> str:
    """Cases as rows, and a total over the cases that ran."""
    columns = _GRAPH_COLUMNS if graph_only else _COLUMNS
    rows = [["case"] + [name for name, _ in columns] + ["seconds"]]
    for case, result in results.items():
        seconds = f"{result.get('seconds', 0):.0f}"
        if "error" in result:
            rows.append([case, "FAILED"] + [""] * (len(columns) - 1) + [seconds])
        else:
            rows.append([case] + [cell(result["scores"]["totals"]) for _, cell in columns] + [seconds])
    scored = [result["scores"]["totals"] for result in results.values() if "scores" in result]
    if len(results) > 1 and scored:
        total = score.add_totals(scored)
        rows.append(["total"] + [cell(total) for _, cell in columns] + [""])
    lines = [table(rows, right=range(1, len(rows[0])))]
    if not graph_only:
        lines.append("impact ok is out of the drivers whose live value matched the answer key; the rest cannot be compared.")
    failed = [case for case, result in results.items() if "error" in result]
    if failed:
        lines.append(f"failed: {', '.join(failed)}")
    return "\n".join(lines)


def table(rows: list[list[str]], right=()) -> str:
    """Rows as aligned columns; the columns in right are right-aligned."""
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    return "\n".join(
        "  ".join(text.rjust(width) if i in right else text.ljust(width) for i, (text, width) in enumerate(zip(row, widths))).rstrip()
        for row in rows
    )


def _of(part: str, whole: str):
    return lambda totals: f"{totals[part]}/{totals[whole]}"


_COLUMNS = [
    ("planted", lambda totals: str(totals["planted"])),
    ("found", _of("found", "planted")),
    ("stale", _of("stale", "planted")),
    ("live ok", _of("live_ok", "planted")),
    ("impact ok", _of("impact_ok", "impact_checked")),
    ("controls ok", _of("controls_ok", "controls")),
    ("false pos", lambda totals: str(totals["false_positives"])),
]
_GRAPH_COLUMNS = [
    ("planted", lambda totals: str(totals["planted"])),
    ("found", _of("found", "planted")),
    ("impact ok", _of("impact_ok", "planted")),
    ("controls found", _of("controls_found", "controls")),
]


def _headline(totals: dict, graph_only: bool) -> str:
    if not graph_only:
        return score.headline(totals)
    n = totals["planted"]
    return f"planted {totals['found']}/{n} found, {totals['impact_ok']}/{n} impact ok at the expected live value"


def _planted(planted: list[dict], graph_only: bool) -> list[str]:
    """A row per planted driver, and under it each output whose impact is off."""
    checks = ["live used"] if graph_only else ["stale", "live", "expected", "live ok"]
    rows, notes = [["planted", "driver", "found"] + checks + ["impact"]], {}
    for p in planted:
        checks = [_num(p["expected_live"])] if graph_only else [_yes(p["stale"]), _num(p["live"]), _expected(p), _live_ok(p)]
        notes[len(rows)] = [
            f"    {_KIND_LABELS[i['kind']]} {_num(i['delta'], signed=True)}, expected {_num(i['expected_at_live'], signed=True)}"
            for i in p["impacts"]
            if not i["ok"]
        ]
        rows.append([p["cell"], _clip(p["driver"]), _yes(p["found"])] + checks + [_impact(p)])
    lines = table(rows).split("\n")
    return [line for i, text in enumerate(lines) for line in [text] + notes.get(i, [])]


def _controls(controls: list[dict]) -> list[str]:
    rows = [["controls", "driver", "found", "flagged"]]
    rows += [[c["cell"], _clip(c["driver"]), _yes(c["found"]), "STALE" if c["stale"] else "no"] for c in controls]
    return table(rows).split("\n")


def _other(other: list[dict]) -> str:
    stale = [o["cell"] for o in other if o["stale"]]
    market = [o["cell"] for o in other if o["market"]]
    return (
        f"other inputs: {len(other)} listed, {sum(o['found'] for o in other)} found, "
        f"{len(stale)} flagged stale{_names(stale)}, {len(market)} labelled market{_names(market)}"
    )


def _false_positives(false_positives: list[dict]) -> list[str]:
    if not false_positives:
        return ["false positives: none"]
    rows = [[f["cell"], _num(f["value"]), f["kind"], f["label"] or ""] for f in false_positives]
    return [f"false positives: {len(rows)}"] + _indent(table(rows).split("\n"))


def _expected(p: dict) -> str:
    return _num(p["expected_live"]) + "".join(f" or {_num(alt)}" for alt in p["alternatives"])


def _live_ok(p: dict) -> str:
    if p["live_ok"]:
        return "ok" if p["matched"] == "primary" else "ok (alternative)"
    if not p["found"]:
        return "-"
    if not p["has_live"]:
        return "no live"
    return f"off {(p['live'] / p['expected_live'] - 1) * 100:+.1f}%" if p["expected_live"] else "off"


def _impact(p: dict) -> str:
    if p["impact_ok"] is None:
        return "-"
    return "ok" if p["impact_ok"] else "OFF"


def _names(cells: list[str]) -> str:
    return f" ({', '.join(cells)})" if cells else ""


def _yes(flag: bool) -> str:
    return "yes" if flag else "NO"


def _num(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "-"
    return f"{value:+.6g}" if signed else f"{value:.6g}"


def _clip(text: str) -> str:
    return text if len(text) <= _DRIVER_WIDTH else text[: _DRIVER_WIDTH - 3] + "..."


def _indent(lines: list[str]) -> list[str]:
    return ["  " + line for line in lines]
