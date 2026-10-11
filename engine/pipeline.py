"""parse → label → check → impact. Produces a report matching schema/constant.schema.json.

start is the fast stage (the workbook's constants and outputs, about a second) and finish the slow one
(labels and web checks, minutes); run does both. refresh recalculates after one constant was edited.

Each constant carries a stage, so a reader can show it as soon as it exists: "labeling" (its label is
still the row's own text), "checking" (labeled, a market input whose check is running) or "done"."""

import contextlib
import copy
import logging
import queue
import threading
from collections.abc import Iterator
from datetime import date
from pathlib import Path

from checks import label, series, news
from graph import constants, impact, parse

log = logging.getLogger(__name__)

_WORKERS = 4  # checks wait on the network
_KEEP = 8  # workbooks kept loaded; an older one is read again from its upload when it is edited

_PATHS: dict[str, Path] = {}  # model_id -> the saved workbook
_LOADED: dict[str, tuple[parse.Workbook, parse.Graph]] = {}
_finishing: set[int] = set()  # id() of each report being finished: a re-upload gets a new report
_GUARD = threading.Lock()  # for the three above
_RECALC = threading.Lock()  # the recalculation library is not thread-safe: one graph.impact call at a time


def run(path: Path, *, model_id: str, filename: str, built_on: str | None = None) -> dict:
    """Both stages, one after the other. Returns the finished report."""
    report = start(path, model_id=model_id, filename=filename, built_on=built_on)
    finish(report)
    return report


def start(path: Path, *, model_id: str, filename: str, built_on: str | None = None, previous: dict | None = None) -> dict:
    """The fast stage: the workbook's constants and outputs, not yet labeled or checked. built_on defaults
    to the date the workbook gives for itself, else today. Raises when path is not a readable workbook.
    Each constant starts with its row's text as a temporary label. previous is this model's report before an
    edit: a constant whose cell, value and surrounding text are unchanged keeps its label and check, so
    finish only labels and checks what the edit touched."""
    wb = parse.load(path)
    graph = parse.build_graph(wb)
    found = constants.find(wb, graph)
    for c in found:
        clues = label.describe(c, wb)
        c["label"] = _temporary_label(clues)
        c["context_key"] = _context_key(c, clues)
        c["stage"] = "labeling"
    if previous:
        _carry(previous.get("constants") or [], found)
    outputs = constants.find_outputs(wb, graph)
    _calc(impact.fill_outputs, wb, graph, outputs)
    _keep(model_id, wb, graph, Path(path))
    today = date.today().isoformat()
    return {
        "model_id": model_id,
        "filename": filename,
        "built_on": built_on or (previous or {}).get("built_on") or parse.model_date(wb) or today,
        "checked_on": today,
        "status": "checking",
        "progress": {"checked": 0, "total": 0},
        "outputs": outputs,
        "constants": found,
        "combined": [],
    }


def finish(report: dict, *, lock=None) -> None:
    """The slow stage, written into the report as it goes: labels, then each market constant's sensitivity,
    check and impact, then combined. Ends with status "done", or "failed" with what was computed so far.
    lock, when given, is held for each write and never across a network call. A second call for a model
    that is being finished, or was, does nothing."""
    lock = lock if lock is not None else contextlib.nullcontext()
    model_id = report["model_id"]
    with _GUARD:
        if report.get("status") != "checking" or id(report) in _finishing:
            return
        _finishing.add(id(report))
    try:
        _finish(report, lock)
    except Exception:
        log.exception("analysis of %s failed", model_id)
        with lock:
            report["status"] = "failed"
    finally:
        with _GUARD:
            _finishing.discard(id(report))


def refresh(report: dict, constant: dict, *, path: Path | None = None) -> None:
    """Recalculate after one constant's label or check changed: its sensitivity (if it has a driver), its
    impact, and the report's combined. path is the workbook of a report that start did not produce here.
    Writes to the report, so a caller that shares it holds its lock."""
    try:
        wb, graph = _model(report["model_id"], path)
    except Exception:
        log.exception("no workbook to recalculate %s with", report["model_id"])
        constant["impact"] = []
        return
    outputs = report["outputs"]
    with _RECALC:
        if constant.get("driver"):
            constant["sensitivity"] = impact.sensitivity(wb, graph, constant, outputs)
        constant["impact"] = impact.deltas(wb, graph, constant, outputs)
        report["combined"] = impact.combined(wb, graph, report["constants"], outputs)


def sensitivity(report: dict, constant: dict, *, path: Path | None = None) -> dict | None:
    """What a small rise in the constant does to the outputs, for a check that is about to run."""
    try:
        wb, graph = _model(report["model_id"], path)
    except Exception:
        log.exception("no workbook to recalculate %s with", report["model_id"])
        return None
    return _calc(impact.sensitivity, wb, graph, constant, report["outputs"])


def _finish(report: dict, lock) -> None:
    wb, graph = _model(report["model_id"])
    found, outputs, built_on = report["constants"], report["outputs"], report["built_on"]

    # labeled on copies: this is an LLM call, and nothing a request can read changes outside the lock.
    # Constants carried over from before an edit are already labeled and checked.
    fresh = [c for c in found if c.get("stage") == "labeling"]
    labeled = copy.deepcopy(fresh)
    try:
        label.apply_all(labeled, wb, graph)  # one LLM call per batch of constants, not one per constant
    except Exception:
        log.exception("labeling failed; constants keep their temporary labels")
    with lock:
        for c, new in zip(fresh, labeled):
            c.update(new)
            c["stage"] = "checking" if c.get("driver") else "done"
        market = [c for c in fresh if c.get("driver")]
        report["progress"]["total"] = len(market)

    # the rest of the model may have moved under a carried check: its effect on the outputs is measured again
    for c in found:
        if c.get("stage") == "done" and c.get("check"):
            deltas = _calc(impact.deltas, wb, graph, c, outputs)
            with lock:
                c["impact"] = deltas

    # measured before the checks so they can reason from which way, and how far, the outputs move
    for c in market:
        measured = _calc(impact.sensitivity, wb, graph, c, outputs)
        with lock:
            c["sensitivity"] = measured

    for c, check in _checks(market, built_on):
        deltas = _calc(impact.deltas, wb, graph, {**c, "check": check}, outputs)
        with lock:
            c["check"], c["impact"], c["stage"] = check, deltas, "done"
            report["progress"]["checked"] += 1

    combined = _calc(impact.combined, wb, graph, found, outputs)
    with lock:
        found.sort(key=lambda c: sum(abs(d["delta"]) for d in c["impact"]), reverse=True)
        report["combined"] = combined
        report["status"] = "done"


# what a constant keeps from before an edit: everything labeling and checking produced
_CARRIED = ("label", "driver", "label_source", "confirmed", "role", "search", "events", "graph_summary", "sensitivity", "check")


def _temporary_label(clues: dict) -> str:
    """The row's own text, and the column's when the row has none: shown until the real label lands."""
    row, col = clues.get("row_label"), clues.get("col_header")
    text = row if isinstance(row, str) and row.strip() else col if isinstance(col, str) and col.strip() else None
    return text.strip() if text else clues["cell"]


def _context_key(c: dict, clues: dict) -> str:
    """Same key, same constant: its place, number and the text around it. A renamed row is a new constant."""
    parts = [c["cell"], c.get("literal_index"), c["value"], c.get("formula"), clues.get("row_label"), clues.get("col_header"), clues.get("row_text_right")]
    return repr(parts)


def _carry(old: list[dict], found: list[dict]) -> None:
    """A constant that was fully labeled and checked, and has not changed, keeps that work."""
    done = {c.get("context_key"): c for c in old if c.get("stage", "done") == "done" and c.get("context_key")}
    for c in found:
        before = done.get(c["context_key"])
        if before is None:
            continue
        for k in _CARRIED:
            if k in before:
                c[k] = copy.deepcopy(before[k])
        c["stage"] = "done"


def _checks(market: list[dict], built_on: str) -> Iterator[tuple[dict, dict | None]]:
    """(constant, its check) as each check finishes, _WORKERS at a time. Each runs on a copy of its
    constant, and on a daemon thread: a ThreadPoolExecutor keeps the process from exiting until every
    check still queued has run."""
    todo: queue.SimpleQueue = queue.SimpleQueue()
    done: queue.SimpleQueue = queue.SimpleQueue()
    for c in market:
        todo.put((c, copy.deepcopy(c)))

    def work() -> None:
        while True:
            try:
                c, snapshot = todo.get_nowait()
            except queue.Empty:
                return
            done.put((c, _check(snapshot, built_on)))

    for _ in range(min(_WORKERS, len(market))):
        threading.Thread(target=work, daemon=True).start()
    for _ in market:
        yield done.get()


def _check(c: dict, built_on: str) -> dict | None:
    """Check one labeled constant. A check that fails leaves the constant unchecked, not the report broken."""
    try:
        if series.handles(c["driver"]):
            return series.check(c, built_on)
        return news.check(c, built_on)
    except Exception:
        log.exception("check failed for %s", c.get("cell"))
        return None


def _calc(function, *args):
    with _RECALC:
        return function(*args)


def remember(model_id: str, path: Path) -> None:
    """Where the model's workbook now lives, after an edit replaced it."""
    with _GUARD:
        _PATHS[model_id] = path


def _keep(model_id: str, wb: parse.Workbook, graph: parse.Graph, path: Path) -> None:
    with _GUARD:
        _PATHS[model_id] = path
        _LOADED.pop(model_id, None)
        _LOADED[model_id] = (wb, graph)
        while len(_LOADED) > _KEEP:
            del _LOADED[next(iter(_LOADED))]


def _model(model_id: str, path: Path | None = None) -> tuple[parse.Workbook, parse.Graph]:
    """The loaded workbook and its graph, read again from the saved file when no longer in memory."""
    with _GUARD:
        loaded = _LOADED.get(model_id)
        path = _PATHS.get(model_id, path)
    if loaded is None:
        if path is None:
            raise LookupError(f"no workbook known for {model_id}")
        wb = parse.load(path)
        loaded = (wb, parse.build_graph(wb))
        _keep(model_id, *loaded, Path(path))
    return loaded
