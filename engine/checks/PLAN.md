# Checks: build plan

Owner: Lucas. Branch: `lucas-check`. The ownership split and the seam with graph are in [`engine/README.md`](../README.md).

For every hardcoded number the graph half finds, checks answers three questions in three parts:

| Part | Question | Example |
|---|---|---|
| 1. Semantic labeling | What is this number? | `Fleet_Model!B11`'s buried `1.2` is "EV collision repair cost relative to a gas car" |
| 2. Scraping | What does the world say about it now? | CCC report via Axios: EV repairs cost about 56% more than gas |
| 3. LLM call (OpenAI) | Is the number wrong, and what should it be? | Stale; suggest `1.56`, with the quote and link |

```
constant (from graph) + wb.context() + graph neighbours
   ▼
1. label.py      label, role, driver, search terms
   ▼  (role == "market" only)
2. scrape.py     Bright Data search + page scrape, FRED if a series exists
   ▼
3. assess.py     OpenAI reads the pages + the constant → JSON
   ▼
   verify.py     quote really on the page? number really in the quote? units sane?
   ▼
   check = { status, live, drift_pct, p_stale, evidence, source }
```

Checks writes `label`, `driver`, `label_source`, `confirmed`, `check` (+ `role`, see below). It never writes `cell`, `value`, `feeds`, `outputs`, `impact`, and never edits the user's file: `live` is a **suggestion** that graph's impact step tries on a copy.

## Test case: the Hertz fleet model

`data/Drift_Hertz_Mock_Fleet_Model.xlsx` (branch `origin/data/hertz-fleet-model`, not yet on `main`). Model built **2022-12-15**, reused **2023-12-04**. The answer key is its `Driver_Map` sheet and `data/ground_truth.md`.

| Cell | What it is | Model | Expected | Verdict |
|---|---|---|---|---|
| `Inputs!B11` | EV residual value, % of cost | 72% | ~50% | stale |
| `Inputs!B12` | Gas car residual value, % of cost | 82% | ~80% | stale |
| `Inputs!B16` | Blended fleet debt cost | 3.40% | ~5.63% | stale |
| `Fleet_Model!B11` (buried `1.2`) | EV vs gas collision repair cost | 1.20x | 1.56x | stale |
| `Fleet_Model!B13/C13` (buried `0.015`) | Auction / remarketing fee | 1.5% | 1.5% | **current** (trap) |
| `Inputs!B8` | Revenue per day | $61 | $58.09 ref | management lever: label, don't update |
| `Inputs!B5–B7, B9–B10, B13–B15, B17–B19` | fleet size, costs, policy, SG&A | | | internal: label only |
| buried `365`, `12`, `1000000` | unit constants | | | not a driver |

What this tells us about the design:

- **There's no fixed list of drivers.** Used EV values, collision repair ratios and auction fees aren't in the old FRED catalog. The label is free text, written by the LLM.
- **Most answers are a percent change, not a level.** 72% × (69.4 / 100) = 49.97%, and 82% × 0.976 = 80.03%. The LLM should look for how much the driver moved between the two dates, and our code applies that move to the cell's value.
- **The check date isn't always today.** This model is checked as of 2023-12-04, so `pipeline.run` needs an `as_of` date (today by default).
- **Only `Inputs` and `Fleet_Model` go in.** `Driver_Map`, `Market_Data`, `Case_Facts`, `Impact_Engine` and `Hertz_Reconciliation` contain the answers. The test copy of the workbook must have those sheets removed, or graph must skip them.

## Files

| File | Holds |
|---|---|
| `label.py` | Part 1: `apply(constant, wb, graph)` |
| `scrape.py` (new) | Part 2: Bright Data search + page fetch, FRED fetch, cache |
| `assess.py` (new) | Part 3: OpenAI prompt and JSON answer |
| `verify.py` (new) | Pure checks on the LLM's answer; no network |
| `openai_client.py` (new) | One `chat_json(messages, schema)` call over `httpx` (no new dependency) |
| `news.py` | Keeps `check(constant, built_on)` as the entry point `pipeline.py` already calls; runs scrape → assess → verify |
| `series.py` | `handles()` returns `False`, so everything goes through `news.check`. FRED moves into `scrape.py` |
| `drivers.py` | Becomes a list of **source hints** (e.g. "used vehicle values" → Manheim, Cox, iSeeCars), not a closed catalog |
| `jev.py` | Removed (replaced by `assess.py`) |
| `app.py` | `PATCH /models/{id}/constants` |

## Part 1: Semantic labeling (`label.py`)

**What it reads.** Everything around the number, from the workbook and from the dependency graph:

| Clue | Where from | Hertz example for the buried `1.2` in `Fleet_Model!B11` |
|---|---|---|
| Row label, column header | `wb.context(cell)` | "Collision and damage ($M)", "EV" |
| Unit and note columns to the right | `wb.values` same row | (on `Inputs` sheet: "% of cost", "KEY ASSUMPTION…") |
| Number format, comment | `wb.context(cell)` | |
| The formula | `constant["formula"]` | `=B6*Inputs!$B$17*1.2/1000000` |
| Labels of the other cells in the formula | `graph.precedents[cell]` → `wb.context()` | "Rental days", "ICE collision and damage cost per rental day" |
| Labels of what it feeds (1–2 steps) | `graph.dependents` → `wb.context()` | "Segment contribution", "Adjusted Corporate EBITDA" |
| Value | `constant["value"]` | 1.2 |

**What it decides.** One OpenAI call per constant (batched: all constants of a workbook in one call is fine, ~20–60 items):

```json
{
  "cell": "Fleet_Model!B11",
  "label": "EV collision repair cost relative to a gas car",
  "role": "market",
  "driver": "ev_collision_cost_ratio",
  "unit": "x",
  "search": ["EV collision repair cost vs gas car", "CCC electric vehicle repair cost"]
}
```

- `role` is one of:
  - `market`: set by the outside world, can go stale. Checked in parts 2 and 3.
  - `lever`: a management choice with a market reference, like revenue per day. Labeled, not updated.
  - `internal`: plan, policy, historical fact, internal cost. Labeled only.
  - `unit`: 365, 12, 1,000,000, 100. Labeled only.
- `driver` is a short slug of the label, so the same driver in two cells is checked once. It's `null` unless `role` is `market`.
- `label_source = "llm"`, `confirmed = false`. Only the user route sets `confirmed = true`.

**Cheap rules before the LLM** (saves calls and can't hallucinate):
- 365, 366, 12, 52, 100, 1000, 1,000,000 inside a formula → `unit`.
- Not covered by a rule → LLM.

**Guardrails.** The LLM answer is parsed against a JSON schema; a bad answer gives `role = "internal"`, `label` = row label. Labels must not be copied from the `Driver_Map` answer key (it isn't in the input).

## Part 2: Scraping (`scrape.py`)

For each **distinct** market `driver` (not each cell):

1. **Bright Data SERP API**: Google search for each `search` term, restricted to the window `built_on` → `as_of` (Google `tbs=cdr:1,cd_min:…,cd_max:…`), news and web results. Keep the top 5–8 URLs.
2. **Bright Data Web Unlocker**: fetch each URL and convert it to plain text. Keep `url`, `publisher`, `date`, `text`, cut to the relevant ~4,000 characters around the search terms.
3. **FRED** (free API), when the label maps to a public series (SOFR, Treasury yields, fed funds, CPI, EUR/USD, WTI): fetch the value at `built_on` and at `as_of`. It goes to the LLM as one more "page", with the FRED URL as its source.
4. Cache everything per `(driver, built_on, as_of)` in `engine/.cache/` so reruns and the demo don't re-scrape.

A failed or empty scrape still goes to part 3, which then answers `unknown`.

## Part 3: LLM call (`assess.py`, OpenAI)

**Input:** the constant (label, value, unit, number format, cell), the dates `built_on` and `as_of`, and the scraped pages with numbered ids.

**Instructions** (summary): say whether the value was still right on `as_of`. Use only the pages given. Every number you use must come from a sentence you copy exactly. Say whether the number you found is a level (1.56x) or a change (-30.6% since Dec 2022). If no page supports a number, say so.

**Output** (OpenAI structured output, strict JSON schema):

```json
{
  "p_stale": 0.9,
  "kind": "level",                       // "level" | "change" | "none"
  "number": 1.56,                        // as written in the quote
  "number_unit": "x",
  "quote": "collision repair on EVs cost about 56% more than on gas cars",
  "page": 3
}
```

**Our code turns it into `live`** (not the LLM):
- `kind = "level"` → convert to the cell's units (`56% more` → 1.56; `5.63%` → 0.0563).
- `kind = "change"` → `live = value × (1 + change)`; e.g. 0.72 × (1 − 0.306) = 0.4997.
- `kind = "none"` → `live = null`, status from `p_stale` alone.

**Model:** `OPENAI_MODEL` env var, `OPENAI_API_KEY` in `.env`. One call per driver; all calls in parallel with `asyncio`.

## Verification (`verify.py`)

A suggestion is kept only if all of these pass; otherwise `live = null` (the `p_stale` flag and the quote can still show):

1. The quote appears word for word (whitespace-normalized) in the text of the page it cites.
2. The number appears in the quote.
3. After conversion, `live` is within 5x of `value` (catches 4.3 vs 0.043 mistakes).

Page dates are not enforced: the search is already limited to `built_on` → `as_of`, and some good sources are published later about the period (the Axios piece on CCC repair costs is dated 2024-01-11).

Then:
- `drift_pct = (live − value) / value × 100`.
- **Status:** `|drift_pct| ≥ threshold` → `stale`, else `current`. With no `live`: `p_stale ≥ 0.7` stale, `≤ 0.3` current, else `unknown`. Threshold: 5% to start; tune against `Driver_Map` column L.
- `check = { kind: "news", status, live, drift_pct, p_stale, as_of, source_name, source_url, evidence: [{quote, url, publisher, date}] }`.

## Confirm/edit route (`app.py`)

```
PATCH /models/{model_id}/constants
{ "cell": "Fleet_Model!B11", "label": "…", "role": "market" }
```

Set `label_source = "user"`, `confirmed = true`, run parts 2–3 again for that constant, recalculate impact through graph, return the updated constant.

## Error handling

- Every part runs inside `try`. On any failure the constant gets `check = {kind: "news", status: "unknown", …}` and the pipeline keeps going.
- No API key → `unknown`, not a crash, so `main` runs without `.env`.

## Tests (no network; OpenAI and Bright Data mocked with saved responses)

| File | Covers |
|---|---|
| `test_checks_label.py` | Hertz contexts → right `role` for all 20 ground-truth rows; unit constants handled by rules without an LLM call |
| `test_checks_verify.py` | real quote kept; made-up quote dropped; number missing from quote dropped; 5.63 vs 0.0563 converted; level vs change math |
| `test_checks_scrape.py` | saved SERP + page responses → cleaned pages; cache hit skips the network |
| `test_checks_hertz.py` | full checks half on the 5 market constants with saved responses: 4 stale, auction fee current |

Real-data runs won't match the synthetic `Market_Data` numbers exactly, so value tests check the **verdict** and the **direction**, with the expected value within a tolerance.

## Build order

| # | Task | Done when |
|---|---|---|
| 1 | `openai_client.py` + label prompt | the 20 Hertz constants (hand-built dicts) get the right `role` |
| 2 | Graph neighbours in the label input | buried `1.2` is labeled as an EV collision cost ratio |
| 3 | `scrape.py` (Bright Data + cache) | real pages come back for "used EV prices 2023" |
| 4 | `assess.py` + `verify.py` | EV residual comes back stale with a real, verified quote |
| 5 | Wire into `news.check` | `POST /models` on the Hertz file gives schema-valid checks |
| 6 | PATCH route | editing a label re-runs its check |

## Needs from others

- **Ethan:** pass `graph` to the labeler: `label.apply(c, wb, graph)`, or better `label.apply_all(found, wb, graph)` once before the loop (runs the LLM calls in parallel). Add `as_of` to `pipeline.run` and pass it to `news.check` (until then, `DRIFT_AS_OF` in `.env` sets it). Skip or strip the answer-key sheets for the Hertz test. Keep `wb` and `graph` per `model_id` for the PATCH route.
- **Team (schema, additive):** new `role` field on each constant; `checked_on` = `as_of`. For `lever` constants (revenue per day), decide whether the reference value shows.
- **Matthew:** merge `data/hertz-fleet-model` into `main`; reconcile the workbook name and dates in `ground_truth.md` (it notes this itself).
- **Keys in `.env`:** `OPENAI_API_KEY`, `OPENAI_MODEL`, `BRIGHTDATA_API_KEY`, Bright Data zone names (`BRIGHTDATA_SERP_ZONE`, `BRIGHTDATA_UNLOCKER_ZONE`), `FRED_API_KEY`.

## Still to verify

- Bright Data request format for the SERP API and Web Unlocker zones on this account, and whether the date-range parameter goes through.
- Which OpenAI model supports strict structured output at the speed we need for ~20 parallel calls.

## Update: graph summary, events, and assumption + prediction

Added after the graph half landed (`build_graph` on `main`). For each market constant:

1. **Graph summary** (`graph_summary.py`). Shortest route from the constant to every output it reaches, as row labels (`Brent crude → Oil-linked cost → COGS → Gross margin → EBITDA`), plus the inputs it is combined with in formulas. The graph is a DAG, so routes are found breadth-first from every cell a copied literal sits in. Built once per workbook from `graph.parse.build_graph`, since `pipeline.py` doesn't pass the graph to checks.
2. **Events** (`label.py`, `scrape.py`). The labeler returns event queries ("Fed rate decision September 2026") as well as figure queries. Pages are tagged `data` (FRED), `figure` or `event`.
3. **Comparison** (`assess.py`). OpenAI gets the graph summary and the tagged pages, and returns the finding as before plus `events` (with direction and exact quote), `effects` (direction per output along the path), `assumption`, `prediction` and `next_steps`.
4. **Verification** (`verify.py`). Event quotes must be on the cited page. A sentence in `assumption`, `prediction` or `next_steps` is dropped if it uses a number that is not the model's value, the verified suggestion or drift, or a number on a source page. A model value of 0 (a 0% tariff) goes stale when a stated rate moves 0.25pp or more.

New fields are additive: `role`, `search`, `events`, `graph_summary` on the constant; `events`, `effects`, `assumption`, `prediction`, `next_steps` on `check`. The README rule "no generated prose on screen" conflicts with `assumption`/`prediction`/`next_steps`; agree with the team before the web app shows them.
