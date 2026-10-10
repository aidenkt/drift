"""Find hardcoded constants and the model's outputs."""


def find(wb, graph) -> list[dict]:
    """Literal cells that formulas depend on, plus literals embedded in formulas.
    Each dict: cell, value, embedded, formula, feeds, outputs (see schema)."""
    raise NotImplementedError


def find_outputs(wb, graph) -> list[dict]:
    """Key result cells (no dependents, or labeled EBITDA / NPV / ...). Each: cell, label, value."""
    raise NotImplementedError
