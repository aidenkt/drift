"""Label a constant with a driver: adjacent row/column headers first, LLM only when ambiguous."""


def apply(constant: dict, wb) -> None:
    """Sets constant['label'], ['driver'], ['label_source'], ['confirmed']."""
    raise NotImplementedError
