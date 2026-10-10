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

    for c in found:
        label.apply(c, wb)
        if c["driver"] and series.handles(c["driver"]):
            c["check"] = series.check(c, built_on)
        elif c["driver"]:
            c["check"] = news.check(c, built_on)
        else:
            c["check"] = None
        c["impact"] = impact.deltas(wb, graph, c, outputs)

    found.sort(key=lambda c: sum(abs(d["delta"]) for d in c["impact"]), reverse=True)
    return {
        "model_id": model_id,
        "filename": filename,
        "built_on": built_on,
        "checked_on": date.today().isoformat(),
        "outputs": outputs,
        "constants": found,
    }
