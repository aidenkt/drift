"""Run the engine on the case-study workbooks and score it against their answer keys. From engine/:

python -m eval.run --graph-only                        the deterministic half only: no keys, no network
python -m eval.run --cases aug2026,airline --jobs 2    the real pipeline, one process per workbook
python -m eval.run --report r.json --truth ../data/ground_truth.md    score a saved report
"""

import argparse
import json
import logging
import os
import re
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path

from eval import score, text, truth

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
DEFAULT_OUT = Path(__file__).resolve().parent / "out"
CASES = ("aug2026", "aug2025", "airline", "coffee", "homebuilder", "trucking")
_SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD", re.IGNORECASE)


def main(argv: list[str] | None = None) -> int:
    args = _arguments(argv)
    if args.report:
        results = {args.report.stem: {"scores": score.score(json.loads(args.report.read_text()), truth.load(args.truth))}}
    else:
        results = run_cases(args.cases, jobs=args.jobs, out=args.out, graph_only=args.graph_only)

    for case, result in results.items():
        print(text.scorecard(case, result, args.graph_only), end="\n\n")
    if not args.report:
        print(text.overall(results, args.graph_only))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(_summary(args, results), indent=1))
    return 1 if any("error" in result for result in results.values()) else 0


def run_cases(cases: list[str], *, jobs: int, out: Path | None, graph_only: bool) -> dict[str, dict]:
    """Case -> result, each case in a process of its own, at most jobs at a time. A case that fails
    is reported and the others carry on."""
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
    if not graph_only:
        print(f"running {len(cases)} cases, {min(jobs, len(cases))} at a time; reports and logs in {out}", file=sys.stderr)
    results = {}
    # a fresh process per workbook: the recalculation library is not thread-safe and keeps state
    with ProcessPoolExecutor(max(1, min(jobs, len(cases))), max_tasks_per_child=1, initializer=_quiet) as pool:
        futures = {pool.submit(run_case, case, out, graph_only): case for case in cases}
        for future in as_completed(futures):
            case = futures[future]
            try:
                results[case] = future.result()
            except Exception as error:
                results[case] = {"error": f"worker died: {type(error).__name__}: {error}"}
            if not graph_only:
                state = "failed" if "error" in results[case] else "finished"
                print(f"[{len(results)}/{len(cases)}] {case} {state} in {results[case].get('seconds', 0):.0f}s", file=sys.stderr)
    return {case: results[case] for case in cases}


def run_case(case: str, out: Path | None, graph_only: bool) -> dict:
    """One workbook: run, save the report, score. Never raises; a failure comes back as {"error", "traceback"}."""
    started = time.perf_counter()
    try:
        key = truth.load(truth_path(case))
        workbook = DATA / key.workbook
        report = graph_report(workbook, key) if graph_only else engine_report(workbook, key, case, out)
        if out is not None:
            (out / f"{case}.json").write_text(json.dumps(report, indent=1, default=str))
        result = {"scores": score.score(report, key)}
    except Exception as error:
        result = {"error": _redact(f"{type(error).__name__}: {error}"), "traceback": _redact(traceback.format_exc())}
    return result | {"seconds": round(time.perf_counter() - started, 1)}


def _quiet() -> None:
    """Runs in each worker before the engine is imported: no progress bars from the recalculation library."""
    os.environ.setdefault("TQDM_DISABLE", "1")


def truth_path(case: str) -> Path:
    return DATA / ("ground_truth.md" if case == "aug2026" else f"ground_truth_{case}.md")


def graph_report(workbook: Path, key: truth.Truth) -> dict:
    """A report from the graph half alone: every planted constant that is found is given the answer
    key's live value and its impact is recalculated. No labels, no checks, no network."""
    from graph import constants, impact, parse

    wb = parse.load(workbook)
    graph = parse.build_graph(wb)
    found = constants.find(wb, graph)
    outputs = constants.find_outputs(wb, graph)
    impact.fill_outputs(wb, graph, outputs)
    for row in key.planted:
        constant = score.find(found, row.cell, row.value)
        if constant is not None:
            constant["check"] = {"kind": "series", "status": "stale", "live": row.live}
            constant["impact"] = impact.deltas(wb, graph, constant, outputs)
    return {
        "model_id": f"graph-only-{workbook.stem}",
        "filename": workbook.name,
        "built_on": key.built_on,
        "checked_on": date.today().isoformat(),
        "outputs": outputs,
        "constants": found,
    }


def engine_report(workbook: Path, key: truth.Truth, case: str, out: Path | None) -> dict:
    """A report from the real pipeline: LLM and web, so it needs the keys in the repo's .env."""
    from dotenv import load_dotenv

    load_dotenv(REPO / ".env")
    if out is not None:
        _log_to(out / f"{case}.log")
    import pipeline

    return pipeline.run(workbook, model_id=f"eval-{case}", filename=workbook.name, built_on=key.built_on)


def _log_to(path: Path) -> None:
    """Send this process's log to a file, with key values blanked: request URLs can carry them."""
    handler = logging.FileHandler(path, mode="w")
    handler.setFormatter(_Redacted("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


class _Redacted(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return _redact(super().format(record))


def _redact(message: str) -> str:
    """The message with the value of every key-like environment variable blanked out."""
    for name, value in os.environ.items():
        if _SECRET_NAME.search(name) and len(value) >= 8:
            message = message.replace(value, "***")
    return message


def _summary(args: argparse.Namespace, results: dict[str, dict]) -> dict:
    scored = [result["scores"]["totals"] for result in results.values() if "scores" in result]
    mode = "report" if args.report else "graph-only" if args.graph_only else "engine"
    return {"mode": mode, "cases": results, "totals": score.add_totals(scored) if scored else None}


def _arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m eval.run", description="Score the engine against the case-study answer keys.")
    parser.add_argument("--report", type=Path, help="score this saved report JSON instead of running the engine (needs --truth)")
    parser.add_argument("--truth", type=Path, help="answer key for --report")
    parser.add_argument("--cases", default=",".join(CASES), help=f"comma-separated, default all: {','.join(CASES)}")
    parser.add_argument("--jobs", type=int, default=3, help="workbooks to run at once (default 3)")
    parser.add_argument("--out", type=Path, help=f"directory for report JSON and logs (default {DEFAULT_OUT} for a real run)")
    parser.add_argument("--graph-only", action="store_true", help="skip the LLM and the web; score found + impact only")
    parser.add_argument("--json", type=Path, help="write the full scores here")
    args = parser.parse_args(argv)
    if bool(args.report) != bool(args.truth):
        parser.error("--report and --truth go together")
    if args.report and args.graph_only:
        parser.error("--graph-only runs the workbooks; it cannot be combined with --report")
    args.cases = list(dict.fromkeys(case.strip() for case in args.cases.split(",") if case.strip()))
    unknown = [case for case in args.cases if case not in CASES]
    if unknown or not args.cases:
        parser.error(f"--cases takes names from {', '.join(CASES)}; got {unknown or 'none'}")
    if args.out is None and not args.graph_only and not args.report:
        args.out = DEFAULT_OUT
    return args


if __name__ == "__main__":
    sys.exit(main())
