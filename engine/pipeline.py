"""parse → label → check → impact. Produces a report matching schema/constant.schema.json."""

from datetime import date
from pathlib import Path

from checks import label, series, news
from graph import constants, impact, parse


def run(path: Path, *, model_id: str, filename: str, built_on: str) -> dict:
    wb = parse.load(path)
    graph = parse.build_graph(wb)
    found = constants.find(wb, graph)
    outputs = constants.find_outputs(wb, graph)
    impact.fill_outputs(wb, graph, outputs)

    for c in found:
        c["check"] = _check(c, wb, graph, outputs, built_on)
        c["impact"] = impact.deltas(wb, graph, c, outputs)

    found.sort(key=lambda c: sum(abs(d["delta"]) for d in c["impact"]), reverse=True)
    return {
        "model_id": model_id,
        "filename": filename,
        "built_on": built_on,
        "checked_on": date.today().isoformat(),
        "outputs": outputs,
        "constants": found,
        "combined": impact.combined(wb, graph, found, outputs),
    }


def _check(c: dict, wb, graph, outputs: list[dict], built_on: str) -> dict | None:
    """Label one constant and check it. A stage that fails leaves the constant unchecked, not the report broken."""
    try:
        label.apply(c, wb)
        if not c["driver"]:
            return None
        # measured before the check so it can reason from which way, and how far, the outputs move
        c["sensitivity"] = impact.sensitivity(wb, graph, c, outputs)
        if series.handles(c["driver"]):
            return series.check(c, built_on)
        return news.check(c, built_on)
    except Exception:
        return None
