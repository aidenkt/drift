# Graph half: implementation plan

Owner: Ethan. Scope: `engine/graph/` and `engine/tests/test_graph_*.py`. [engine_plan.md](engine_plan.md) has the ownership split and the seam with the checks half; [overall_plan.md](overall_plan.md) has the product plan and the day's schedule.

## Rules that keep this conflict-free

1. **New code goes in new files.** Everything below lives in `engine/graph/` or in `engine/tests/test_graph_*.py`. Nobody else writes there.
2. **The five function signatures `pipeline.py` already calls do not change:** `parse.load(path)`, `parse.build_graph(wb)`, `constants.find(wb, graph)`, `constants.find_outputs(wb, graph)`, `impact.deltas(wb, graph, constant, outputs)`. New capability is added as new functions, never by changing these.
3. **`pipeline.py` gets two small edits, each its own commit, merged the same hour:** the stage-tolerance wrapper (milestone 3) and the combined-run call (milestone 5). No other edits to shared files.
4. **Never touch from this branch:** `checks/`, `app.py`, `web/`, `schema/constant.schema.json`, `web/src/types.ts`. No new dependencies are needed, so `pyproject.toml` stays untouched too.
5. **New report fields are additive.** The schema does not forbid extra properties, so `literal_index` on a constant and `combined` at the top level validate today. Emit them now; add them to the schema later in one agreed commit with the fixture and `types.ts`.
6. **Merge to `main` at the end of every milestone,** after `pytest` passes. Small merges, often.

## Before starting

- **Python:** done. System `python3` is 3.9.6, so the venv is `engine/.venv` from conda `transformer` (Python 3.12.14). `formulas` 1.3.4 only lists support through 3.13, so do not use conda base (3.14). Activate with `source engine/.venv/bin/activate`.
- **`formulas` spike:** passed on 1.3.4 with the plain `formulas` dependency (no `[excel]` extra; `openpyxl` is already direct). Cell ids are `'[file.xlsx]SHEET'!A1`: the sheet is upper case, the filename keeps its on-disk case. `NPV` and `IRR` matched `numpy-financial` (4.132231 and 0.130662), and overriding the rate from 10% to 5% moved NPV from 4.132231 to 11.564626. Compiling the six-cell book took 2.9s; a later `calculate` was 1ms. Milestone 4 stays a real recalculation. The path-only fallback remains only if a later workbook has cycles or an unsupported function.

## Files

| File | Holds | Depends on |
|---|---|---|
| `graph/refs.py` (new) | Cell keys (`Sheet!A1`), reference parsing, range expansion | nothing |
| `graph/parse.py` | `Workbook`, `Graph`, `load`, `build_graph` | `refs` |
| `graph/context.py` (new) | Row label, column header, format, comment for a cell | `parse` |
| `graph/constants.py` | `find`, `find_outputs` | `parse`, `context` |
| `graph/recalc.py` (new) | The only file that imports `formulas`: hoist, compile, calculate | `parse` |
| `graph/impact.py` | `deltas`, `combined` | `recalc` |

`recalc.py` isolates the library: if `formulas` has to be swapped for something else, only that file changes.

## Data structures

```python
# graph/parse.py
@dataclass
class Workbook:
    path: Path
    sheets: list[str]
    formulas: dict[str, str]      # "Sheet!A1" -> "=B5*1.08", formula cells only
    values: dict[str, object]     # every non-empty cell: literal, or Excel's cached result
    formats: dict[str, str]       # Excel number format string
    comments: dict[str, str]
    bounds: dict[str, tuple]      # used area per sheet, for clipping whole-column ranges
    def context(self, cell: str) -> dict: ...   # delegates to graph/context.py

@dataclass
class Literal:
    cell: str        # the formula cell
    index: int       # position among the number literals in that formula
    value: float

@dataclass
class Graph:
    precedents: dict[str, set[str]]   # cell -> cells it reads
    dependents: dict[str, set[str]]   # cell -> cells that read it
    literals: dict[str, list[Literal]]
    cycles: list[list[str]]
    def downstream(self, cell: str) -> set[str]: ...   # transitive dependents
```

Cell keys are `Sheet!A1` everywhere, with no `$` and no quotes, matching the `cell` examples in the schema.

## Milestones

Each one ends with something another person can use.

### 1. Parse and context (target 1:50)

- `refs.py`: normalize a reference to a key, split `'My Sheet'!$B$4`, expand `A1:C3`.
- `parse.load`: open with openpyxl twice (`data_only=False` for formulas, `data_only=True` for cached values) and fill `Workbook`.
- `context.py`: nearest text cell to the left in the row, nearest text cell above in the column, number format, comment. Returns the dict shape in [engine_plan.md](engine_plan.md).
- **Tests** (`test_graph_parse.py`): keys for quoted and cross-sheet names; context on a small assumptions table.
- **Unblocks:** the checks owner can replace the hand-written context dict with `wb.context()`.

### 2. Graph, constants, outputs (target 2:40)

- `parse.build_graph`: run each formula through `openpyxl.formula.tokenizer.Tokenizer`.
  - Range operands become edges. Expand ranges, clip whole-column and whole-row ranges to `bounds`, resolve defined names, and skip references to other workbooks.
  - Number operands become `Literal`s. A leading `-` is a separate operator token, and `5%` is the number 5 followed by a `%` operator; fold both into the literal's value.
  - Find cycles with a depth-first search and record them.
- `constants.find`:
  - **Cell inputs:** numeric, not a formula, at least one dependent. Skip dates, booleans, and integers 1900–2100 whose row neighbours are also years.
  - **Embedded literals:** skip 0, 1 and -1, and skip arguments in structural positions (`ROUND` digits, `VLOOKUP` column index, `INDEX`, `OFFSET`, `LEFT`, `RIGHT`, `MID`).
  - **Fields set:** `cell`, `value`, `embedded`, `formula`, `feeds`, `outputs`, plus `literal_index` for embedded ones. The checks fields get neutral defaults (`label: ""`, `driver: None`, `label_source: "header"`, `confirmed: False`, `check: None`, `impact: []`) so the dict is schema-valid before labeling runs.
- `constants.find_outputs`: formula cells whose row label matches EBITDA, NPV, IRR, net income or gross margin, taking the rightmost formula cell of each such row. If nothing matches, fall back to numeric formula cells with no dependents, capped at 10.
- **Tests** (`test_graph_constants.py`): the `=B5*1.08` case; a constant reached only through a `SUM` range; year headers skipped; `ROUND(x, 2)` skipped; two literals in one formula get different `literal_index`; `feeds` and `outputs` on a three-level chain.
- **Unblocks:** real constants for the labeler and the web app; Matthew can check detection against his ground-truth table.

### 3. Pipeline runs end to end (target 3:00, Sense Check 2)

- In `pipeline.py`, wrap each label, check and impact call so a stage that raises leaves `check: None` or `impact: []`.
- **Test** (`test_graph_pipeline.py`): run the pipeline on a pytest-built workbook and validate the result against the schema.
- **Unblocks:** `POST /models` works on a real upload, with or without the checks half finished.

### 4. Impact, one at a time (target 5:00)

- `recalc.hoist(wb, graph)`: write a temp copy of the workbook with a scratch sheet `_drift`. Each embedded literal moves to its own `_drift` cell and the formula is rewritten to reference it, rebuilt from the tokenizer's tokens. After this every constant is a plain input cell.
- `recalc.compile(wb, graph)`: compile the temp copy once and cache the result on the `Workbook` object.
- `recalc.calculate(model, overrides, outputs)`: one call, returns output values.
- **Baseline check:** calculate with no overrides and compare to the cached values in `wb.values`. An output that does not match within a small tolerance is marked untrusted and gets no impact.
- `impact.deltas`: if `constant["check"]` has a numeric `live`, override that one input and return `[{output, delta}]` for trusted outputs the constant reaches. Otherwise return `[]`.
- **Fallback:** if the graph has cycles, compiling fails, or a function is unsupported, `deltas` returns `[]`. `feeds` and `outputs` still show the dependency path.
- **Tests** (`test_graph_impact.py`): a cell input and an embedded literal on a hand-computable model; `live: None` gives `[]`; a workbook with a cycle gives `[]`.

### 5. Combined run and fixture (target 6:00, Sense Check 3)

- `impact.combined(wb, graph, constants, outputs)`: one run with every live value applied; returns `[{output, delta}]`.
- One line in `pipeline.py` adds it to the report as top-level `combined`.
- Regenerate `schema/fixtures/case_study.json` from real engine output once Matthew's workbook is in. This is a shared file, so do it as its own commit and tell Aiden first.
- Fill in `tests/test_case_study.py` for the graph side: every planted constant in the ground-truth table is detected.

## How later work plugs in

| New thing | Where it goes | What stays untouched |
|---|---|---|
| A new driver or data source | `checks/` only | all of `graph/` |
| User edits a label or value | `app.py` re-runs check, then calls `impact.deltas` again; the compiled model is cached | `parse`, `constants` |
| A different recalculation engine | `recalc.py` | `impact.py` and everything upstream |
| A new detection rule (say, grouping a row of yearly inputs) | a new function in `constants.py`, called from `find` | `parse`, `impact` |
| Showing the path from input to output | `Graph.downstream` already has it; add a function returning the ordered path | everything else |
| Saved audits | the report dict is plain JSON, so storage wraps `pipeline.run` | `graph/` |

## Risks

| Risk | What happens |
|---|---|
| `formulas` cannot compile the case study | Path-only fallback; found in the spike, before any impact code is written |
| Workbook has no cached values (generated by openpyxl, never saved from Excel) | Baseline check has nothing to compare; trust the recalculation and flag the report. Ask Matthew to save from Excel |
| Checks half writes `live` in the wrong units | Impact is wrong silently. The seam rule makes this the checks half's job; add a sanity guard that skips impact when `live` differs from `value` by more than 100x |
| Detection is too noisy (unit conversions like 12 or 1000) | Tune the skip list against Matthew's ground-truth table, not by guesswork |
