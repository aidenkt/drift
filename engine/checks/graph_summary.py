"""Step 1: what a constant drives, read off the dependency graph.

The graph is a DAG, not a tree: one constant can reach an output along several routes, and many
constants feed the same cells. For each output the constant reaches we keep the shortest route, and we
list the other inputs it is combined with, so the LLM can reason about which way an event pushes the outputs.
"""

from collections import deque

from graph import parse

MAX_PARTNERS = 8

_graphs: dict[int, object] = {}


def graph_for(wb):
    """The workbook's dependency graph, built once per workbook (pipeline.py doesn't pass it to checks)."""
    key = id(wb)
    if key not in _graphs:
        _graphs[key] = parse.build_graph(wb)
    return _graphs[key]


def summarize(constant: dict, wb, graph) -> dict:
    """{"paths": [{"output", "output_label", "path": [labels], "cells": [cells]}], "combined_with": [labels]}"""
    start = constant.get("cells") or [constant["cell"]]
    outputs = constant.get("outputs") or []
    routes = _shortest_routes(graph, start, set(outputs))
    paths = []
    for output in outputs:
        route = routes.get(output)
        if route:
            labels = _collapse([_label(wb, c) for c in route])
            paths.append({"output": output, "output_label": labels[-1], "path": labels, "cells": route})
    return {"paths": paths, "combined_with": _partners(constant, wb, graph, start)}


def describe_paths(summary: dict) -> list[str]:
    """One line per output, e.g. "Brent crude ($/bbl) → Oil-linked cost → COGS → EBITDA"."""
    return [" → ".join(p["path"]) for p in summary.get("paths", [])]


def _shortest_routes(graph, start: list[str], targets: set[str]) -> dict[str, list[str]]:
    """Breadth-first over dependents from every start cell; the first time a target is reached is its shortest route."""
    parent: dict[str, str | None] = {c: None for c in start}
    queue = deque(start)
    found: dict[str, list[str]] = {}
    while queue and len(found) < len(targets):
        cell = queue.popleft()
        if cell in targets and cell not in found:
            route, node = [], cell
            while node is not None:
                route.append(node)
                node = parent[node]
            found[cell] = route[::-1]
        for nxt in sorted(graph.dependents.get(cell, ())):
            if nxt not in parent:
                parent[nxt] = cell
                queue.append(nxt)
    return found


def _partners(constant: dict, wb, graph, start: list[str]) -> list[str]:
    """Labels of the other inputs this constant is combined with in a formula."""
    if constant.get("embedded"):
        # a literal sits inside its own formula: the formula's other references are its partners
        cells = set().union(*(graph.precedents.get(c, set()) for c in start))
    else:
        cells = set()
        for c in start:
            for dependent in graph.dependents.get(c, ()):
                cells |= graph.precedents.get(dependent, set())
        cells -= set(start)
    labels = []
    for c in sorted(cells):
        text = _label(wb, c)
        if text and text not in labels:
            labels.append(text)
    return labels[:MAX_PARTNERS]


def _label(wb, cell: str) -> str:
    try:
        ctx = wb.context(cell) or {}
    except Exception:
        ctx = {}
    return ctx.get("row_label") or cell


def _collapse(labels: list[str]) -> list[str]:
    """Drop repeats in a row (the same line item across year columns)."""
    out = []
    for label in labels:
        if not out or out[-1] != label:
            out.append(label)
    return out
