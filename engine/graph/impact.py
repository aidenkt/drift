"""Recalculate outputs with constants set to their live values."""

import math
from dataclasses import dataclass, field

from graph import recalc

_REL_TOL = 1e-6  # cached values exported from Google Sheets are rounded to 10 significant digits
_ABS_TOL = 1e-9
_MAX_RATIO = 100  # a live value this many times larger or smaller than the constant is in other units


@dataclass
class _State:
    model: recalc.Model
    # recalculated cells per set of overrides; () is the baseline
    runs: dict[tuple, dict[str, float | None]] = field(default_factory=dict)


def deltas(wb, graph, constant, outputs) -> list[dict]:
    """[{output, delta}]: the change in each output the constant reaches when it is set to its live value.
    Empty without a usable live value, or when the workbook cannot be recalculated."""
    try:
        state = _state(wb, graph)
        overrides = _overrides(state, constant)
        if not overrides:
            return []
        reach = set(constant.get("outputs") or ())
        baseline = _trusted(wb, state, outputs)
        cells = [cell for cell in baseline if cell in reach]
        after = _values(state, overrides, cells)
        return [{"output": cell, "delta": after[cell] - baseline[cell]} for cell in cells if after[cell] is not None]
    except Exception:
        return []


def combined(wb, graph, constants, outputs) -> list[dict]:
    """[{output, delta}] for every output with all the constants that have an impact set to their
    live values at once."""
    try:
        state = _state(wb, graph)
        overrides: dict[str, float] = {}
        for constant in constants:
            if deltas(wb, graph, constant, outputs):
                overrides.update(_overrides(state, constant))
        if not overrides:
            return []
        baseline = _trusted(wb, state, outputs)
        cells = list(baseline)
        after = _values(state, overrides, cells)
        return [{"output": cell, "delta": after[cell] - baseline[cell]} for cell in cells if after[cell] is not None]
    except Exception:
        return []


def fill_outputs(wb, graph, outputs) -> None:
    """Give outputs of a workbook that was never calculated their recalculated value."""
    try:
        state = _state(wb, graph)
        if state is None:
            return
        missing = [output for output in outputs if wb.values.get(output["cell"]) is None]
        values = _values(state, {}, [output["cell"] for output in missing])
        for output in missing:
            if values[output["cell"]] is not None:
                output["value"] = values[output["cell"]]
    except Exception:
        return


def _state(wb, graph) -> _State | None:
    """The compiled workbook, built on first use and kept on wb. None when it has circular references
    or does not compile; that is remembered too."""
    if "_recalc" not in vars(wb):
        wb._recalc = _build(wb, graph)
    return wb._recalc


def _build(wb, graph) -> _State | None:
    from graph import constants

    if graph.cycles or recalc.too_big(wb):
        return None
    try:
        literals = [
            (cell, constant["literal_index"])
            for constant in constants.find(wb, graph)
            if constant["embedded"]
            for cell in _cells(constant)
        ]
        model = recalc.compile(wb, literals)
    except Exception:
        return None
    return _State(model) if model is not None else None


def _cells(constant: dict) -> list[str]:
    """Formula cells an embedded constant is written in."""
    return constant.get("cells") or [constant["cell"]]


def _overrides(state: _State | None, constant: dict) -> dict[str, float]:
    """Cell -> live value for one constant. {} when there is nothing to recalculate."""
    live = _live(constant)
    if state is None or live is None:
        return {}
    if not constant.get("embedded"):
        return {constant["cell"]: live}
    scratch = [state.model.scratch.get((cell, constant.get("literal_index"))) for cell in _cells(constant)]
    return {} if None in scratch else dict.fromkeys(scratch, live)


def _live(constant: dict) -> float | None:
    """The live value when it is a finite number in the same units as the constant."""
    check = constant.get("check")
    live = check.get("live") if isinstance(check, dict) else None
    if not _is_number(live):
        return None
    value = constant.get("value")
    if _is_number(value) and value and live and not 1 / _MAX_RATIO <= abs(live / value) <= _MAX_RATIO:
        return None
    return float(live)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _trusted(wb, state: _State, outputs: list[dict]) -> dict[str, float]:
    """Recalculated baseline of the outputs whose value Excel agrees with, or never calculated."""
    cells = [output["cell"] for output in outputs]
    baseline = _values(state, {}, cells)
    trusted = {}
    for cell in cells:
        value, cached = baseline[cell], wb.values.get(cell)
        if value is None:
            continue
        if cached is None or (_is_number(cached) and math.isclose(cached, value, rel_tol=_REL_TOL, abs_tol=_ABS_TOL)):
            trusted[cell] = value
    return trusted


def _values(state: _State, overrides: dict[str, float], cells: list[str]) -> dict[str, float | None]:
    """Recalculated cells under the overrides, remembered so that a repeated question costs nothing."""
    run = state.runs.setdefault(tuple(sorted(overrides.items())), {})
    missing = [cell for cell in cells if cell not in run]
    if missing:
        run.update(recalc.calculate(state.model, overrides, missing))
    return run
