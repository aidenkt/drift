"""parse → label → check → impact. Produces a report matching schema/constant.schema.json.

start is the fast stage (the workbook's constants and outputs, about a second) and finish the slow one
(labels and web checks, minutes); run does both. refresh recalculates after one constant was edited."""

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
_finishing: set[str] = set()
_GUARD = threading.Lock()  # for the three above
_RECALC = threading.Lock()  # the recalculation library is not thread-safe: one graph.impact call at a time


def run(path: Path, *, model_id: str, filename: str, built_on: str | None = None) -> dict:
    """Both stages, one after the other. Returns the finished report."""
    report = start(path, model_id=model_id, filename=filename, built_on=built_on)
    finish(report)
    return report


def start(path: Path, *, model_id: str, filename: str, built_on: str | None = None) -> dict:
    """The fast stage: the workbook's constants and outputs, not yet labeled or checked. built_on defaults
    to the date the workbook gives for itself, else today. Raises when path is not a readable workbook."""
    wb = parse.load(path)
    graph = parse.build_graph(wb)
    found = constants.find(wb, graph)
    outputs = constants.find_outputs(wb, graph)
    _calc(impact.fill_outputs, wb, graph, outputs)
    _keep(model_id, wb, graph, Path(path))
    today = date.today().isoformat()
    return {
        "model_id": model_id,
        "filename": filename,
        "built_on": built_on or parse.model_date(wb) or today,
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
        if report.get("status") != "checking" or model_id in _finishing:
            return
        _finishing.add(model_id)
    try:
        _finish(report, lock)
    except Exception:
        log.exception("analysis of %s failed", model_id)
        with lock:
            report["status"] = "failed"
    finally:
        with _GUARD:
            _finishing.discard(model_id)


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

    # labeled on copies: this is an LLM call, and nothing a request can read changes outside the lock
    labeled = copy.deepcopy(found)
    try:
        label.apply_all(labeled, wb, graph)  # one LLM call per batch of constants, not one per constant
    except Exception:
        log.exception("labeling failed; constants keep their neutral labels")
    with lock:
        for c, new in zip(found, labeled):
            c.update(new)
        market = [c for c in found if c.get("driver")]
        report["progress"]["total"] = len(market)

    # measured before the checks so they can reason from which way, and how far, the outputs move
    for c in market:
        measured = _calc(impact.sensitivity, wb, graph, c, outputs)
        with lock:
            c["sensitivity"] = measured

    for c, check in _checks(market, built_on):
        deltas = _calc(impact.deltas, wb, graph, {**c, "check": check}, outputs)
        with lock:
            c["check"], c["impact"] = check, deltas
            report["progress"]["checked"] += 1

    combined = _calc(impact.combined, wb, graph, found, outputs)
    with lock:
        found.sort(key=lambda c: sum(abs(d["delta"]) for d in c["impact"]), reverse=True)
        report["combined"] = combined
        report["status"] = "done"


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
