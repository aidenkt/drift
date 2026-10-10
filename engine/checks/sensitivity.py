"""Dollar impact the LLM can see: what a 10% rise in a constant does to each output it reaches.

The exact impact (graph/impact.py) needs the live value, which only exists after the LLM has answered.
A fixed bump gives the LLM direction and size for every constant, before it writes its suggestion,
using the same recalculation engine.
"""

from graph import constants as graph_constants
from graph import impact

BUMP = 0.10  # +10%
BUMP_FROM_ZERO = 0.01  # a constant at 0 (a 0% tariff) is bumped by one point instead

_outputs: dict[int, list[dict]] = {}


def for_constant(constant: dict, wb, graph) -> dict | None:
    """{"change": "+10%", "from", "to", "outputs": [{output, label, value, delta}]} or None if the model
    can't be recalculated."""
    value = float(constant["value"])
    to = value * (1 + BUMP) if value else BUMP_FROM_ZERO
    probe = {**constant, "check": {"live": to}}
    outputs = _outputs_for(wb, graph)
    deltas = impact.deltas(wb, graph, probe, outputs)
    if not deltas:
        return None
    by_cell = {o["cell"]: o for o in outputs}
    return {
        "change": f"+{BUMP:.0%}" if value else f"+{BUMP_FROM_ZERO:g}",
        "from": value,
        "to": to,
        "outputs": [
            {"output": d["output"], "label": by_cell[d["output"]]["label"],
             "value": by_cell[d["output"]]["value"], "delta": round(d["delta"], 6)}
            for d in deltas
        ],
    }


def _outputs_for(wb, graph) -> list[dict]:
    key = id(wb)
    if key not in _outputs:
        outputs = graph_constants.find_outputs(wb, graph)
        impact.fill_outputs(wb, graph, outputs)
        _outputs[key] = outputs
    return _outputs[key]
