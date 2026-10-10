# Engine: backend plan and who owns what

Two people work on the engine. This file says who owns which files, what passes between the two halves, and the order to build in. The root [README](../README.md) covers setup and the project rules.

## What the engine does

`pipeline.run()` takes an uploaded `.xlsx` and returns one report matching [`schema/constant.schema.json`](../schema/constant.schema.json):

1. **Parse** the workbook and build the cell dependency graph.
2. **Find constants**: hardcoded numbers that formulas depend on, including literals inside formulas such as the `1.08` in `=B5*1.08`. Find the output cells (EBITDA, NPV, ...).
3. **Label** each constant with a real-world driver from the fixed catalog, or leave it unmapped if it is internal (growth targets, headcount).
4. **Check** each labeled constant against live data: FRED for series drivers, Bright Data news plus Jev for the rest.
5. **Impact**: recalculate the outputs with each constant set to its live value, one at a time and all together.

Steps 1, 2 and 5 are the graph half. Steps 3 and 4 are the checks half.

## Ownership

| | Graph owner (Ethan) | Checks owner |
|---|---|---|
| Folder | `graph/` | `checks/` |
| Files | `parse.py`, `constants.py`, `impact.py`, `pipeline.py` | `label.py`, `drivers.py`, `series.py`, `news.py`, `jev.py`, `app.py` |
| Tests | `tests/test_graph_*.py` | `tests/test_checks_*.py` |
| Question it answers | What is hardcoded, what does it feed, and what happens to the outputs if it changes? | What does this number stand for, what is it today, and is it stale? |

Neither person edits the other's folder. If something in the other half needs to change, ask for it.

### Graph owner

- **Parsing:** load with openpyxl twice (formulas and cached values) into one wrapper object keyed by `Sheet!A1`.
- **Graph:** tokenize each formula with openpyxl's `Tokenizer` to get cell references and number literals in one pass. Handle `$` refs, quoted and cross-sheet names, ranges and defined names. Clip whole-column ranges to the used area. Detect cycles.
- **Constants:** numeric non-formula cells with at least one dependent, skipping dates, booleans and 1900–2100 integers in header rows. For embedded literals, skip 0, 1 and -1 and structural arguments (`ROUND` digits, `VLOOKUP` column index, `INDEX`/`OFFSET`/`LEFT`/`MID`).
- **Outputs:** formula cells with no dependents whose row label matches EBITDA, NPV, IRR, net income or gross margin.
- **Reach:** `feeds` and `outputs` per constant, from a BFS over the reverse graph.
- **Context:** `wb.context(cell)` for the labeler (see below). Raw text only, no interpretation.
- **Impact:** move every embedded literal into a cell on a scratch sheet in a temp copy, so every constant is a plain input cell. Compile once with the `formulas` library, then run one override per constant plus one run with all of them. Compare the recalculated baseline to Excel's cached values and drop impact for any output that does not match. If the model has cycles or unsupported functions, return `impact: []`.

### Checks owner

- **Labeling:** map each constant to a key in `drivers.py`. Match on the row and column headers first; call the LLM only when that is ambiguous. Internal inputs get `driver: null`.
- **Live values:** FRED for `series` drivers; Bright Data plus Jev for `news` drivers, with source and evidence quotes.
- **Unit normalization:** convert the live value into the cell's units before writing it. Covers percent vs decimal (4.5 vs 0.045), FX inversion (EUR/USD vs USD/EUR) and a spread over a base rate (the cell holds SOFR + 2.25%, the source gives SOFR).
- **Staleness:** `drift_pct` and the `stale` / `current` / `unknown` status.
- **Confirm/edit endpoint:** the route for a user changing or confirming a label, since it re-triggers the check.

## The seam

The only thing that passes between the two halves is the constant dict from the schema, plus one helper.

**Fields**

| Written by graph, read-only for checks | Written by checks, read-only for graph |
|---|---|
| `cell`, `value`, `embedded`, `formula`, `feeds`, `outputs`, `impact` | `label`, `driver`, `label_source`, `confirmed`, `check` |

**`check.live` is always in the same units as `value`.** The checks half converts before writing it, so the impact step substitutes the number as is. If the live value cannot be converted, set `live` to `null`; impact for that constant is then empty.

**An embedded constant can cover several cells.** A literal copied across a row, such as `=0.0366+Assumptions!$B$29` in `P&L!C35:G35`, is one constant, not five. Its `cell` is the range string `"P&L!C35:G35"`, and two extra fields say where it lives: `cells` (every formula cell, left to right) and `literal_index` (which number in the formula). Typed numbers in cells are never grouped. `wb.context()` accepts the range string and describes its first cell.

**The report has a top-level `combined` list** of `{output, delta}`: every live value applied at once. `cells`, `literal_index` and `combined` are extra fields the schema allows but does not list yet.

**`wb.context(cell)`** returns what the labeler needs to read the cell:

```python
wb.context("Assumptions!C14")
# {
#   "sheet": "Assumptions",
#   "row_label": "EUR/USD rate",      # nearest text to the left in the row, or None
#   "col_header": "FY2026",           # nearest text above in the column, or None
#   "number_format": "0.00",          # Excel format string: tells % from $ from x
#   "comment": None,
# }
```

## Working in parallel

- **Checks starts against the fixture.** Use the constants in [`schema/fixtures/case_study.json`](../schema/fixtures/case_study.json) and a hand-written dict in place of `wb.context()`. The parser is not needed.
- **Graph tests impact against made-up `check.live` values.** FRED and Bright Data are not needed.
- **Graph lands `wb.context()` first,** even if it only returns the row label, so the stand-in can be swapped out early.
- **A missing stage does not break the pipeline.** A stage that raises gives `check: null` or `impact: []`, so `main` always runs.
- **Graph tests build tiny workbooks with openpyxl inside pytest,** so nothing waits on the case-study file.
- **Both run `tests/test_schema.py` before merging.**
- **Schema changes need both engine owners and Aiden,** with the schema, the fixture and `web/src/types.ts` in one commit.

## Build order

| When (PT) | Graph | Checks |
|---|---|---|
| Before Sense Check 2 (3:00) | Parse, graph, constants, outputs, `wb.context()`. `POST /models` returns a schema-valid report with real constants. | Header labeling, FRED series check with normalization and drift status. |
| 4:00–6:00 | Impact: one at a time and combined. Regenerate the fixture from real engine output. | LLM labeling fallback, news checks with Jev, confirm/edit endpoint. |

## Open decisions

These touch the shared schema, so settle them together.

- **Embedded constants have no unique id.** `cell` is the formula's cell, so two literals in one formula collide. Proposal: an optional `literal_index` field (position of the literal in the formula).
- **News checks return `live: null`,** so freight and tariff cannot have impact, though the placeholder fixture shows impact for freight. Either the news check extracts a number, or those rows show the dependency path only.
- **The combined run has nowhere to live.** The schema holds one-at-a-time deltas only. Proposal: a top-level `combined` list of `{output, delta}`; the gap between it and the sum of the individual deltas is the interaction effect.
- **Fetching runs before confirmation.** The pipeline goes straight from label to check; the original plan says nothing is fetched until a person confirms the labels. Changing this splits `POST /models` into two calls.
- **The case-study workbook must be saved from Excel.** A file generated by openpyxl and never opened in Excel has no cached values, so the baseline check has nothing to compare against.
