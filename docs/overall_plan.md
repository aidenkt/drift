Idea 2 build plan: assumption staleness audit
Ship v1 by noon as input labeling plus one live fetch; by 8pm, a full audit showing which stale assumptions move the model's key output, and by how much.
Product
User: an FP&A or financial analyst who maintains operating models and reuses them months later.
The one task: the refresh check before an old model is reused for a reforecast, a lender update or an investment memo. Today that means scanning every input tab by memory and hoping nothing went stale.
One-line pitch: upload a model, and see which hardcoded assumptions the world has moved past, with a source for each and how much each one changes your answer.
Working name: Drift (placeholder).
How it works
The LLM only labels and explains; every number comes from the workbook or a cited source, and nothing is fetched until a person confirms the labels.
Core logic
Six steps, each deterministic except labeling, which a human confirms.
1. Find the inputs. Parse every cell and build the dependency graph from formula references.
    ◦ An input is a numeric constant that at least one formula depends on.
    ◦ Also flag constants buried inside formulas, such as =B5*1.08.
    ◦ Skip years, period headers and row numbers (integers 1900–2100 in header rows).
2. Gather context per input. Collect the nearest text label in the row, the column header, the sheet name, the number format (%, $, x) and any cell comment.
3. Label the driver (LLM). Return structured JSON per input: cell, label, driver_type, series (e.g. "EUR/USD spot"), unit, search_query, confidence, reason. Non-market inputs (headcount plan, management targets) are tagged internal and skipped. The user confirms or edits each label; this is the trust step.
4. Fetch the current value. Use Bright Data to pull the value from a known source URL per driver type, falling back to a search query. Store the value, source URL, snippet and timestamp, and show the snippet so the user can verify it.
5. Normalize, then compare. Handle units before computing drift, since this is where silent errors live:
    ◦ 0.045 vs 4.5%
    ◦ EUR/USD vs USD/EUR (invert)
    ◦ per barrel vs per ton, monthly vs annual
6. Measure impact. Find output cells (no dependents, labeled NPV, EBITDA, IRR, net income). Recalculate with each updated input one at a time, then all together, to get a bridge: "EBITDA falls $1.2M; $0.8M from freight, $0.4M from FX." v1 fallback: show the dependency path from input to output without recalculating.
Driver taxonomy for v1 (8 types): FX rate, interest rate, commodity price, freight rate, tariff rate, inflation, competitor price, wage or hiring proxy.
Stack
Each sponsor gets one clear job, so the pitch never feels like sponsor bingo.
Piece
Job
Notes
Base44
Upload screen, review table, report page, saved audits
Confirm at Ore's workshop how it calls external APIs and MCPs
Daytona
Runs Python on uploaded workbooks: parsing, graph, recalculation
openpyxl + formulas library; keeps untrusted files sandboxed
Bright Data
Fetches current driver values with a source URL
SERP API or Web Unlocker; one curated source URL per driver type
LLM
Labels inputs with drivers; writes the plain-English report
Never produces a number; only labels and explains
MongoDB
Audit history: inputs, labels, fetched values, sources
Optional if Base44's built-in storage is enough
If Base44 can't call Daytona, parse in a Base44 backend function with SheetJS, which reads formulas, and drop recalculation to the v1 dependency-path fallback.
Demo model
Build one small workbook for a fictional US importer of European goods, with assumptions deliberately left at early-2024 values so drift is visible. Every tester can follow it in 30 seconds.
Input
Driver type
Why it's in the demo
EUR/USD rate
FX rate
Tests the inversion trap (EUR/USD vs USD/EUR)
Revolver rate (SOFR + spread)
Interest rate
The terminal-data case; shows decimal vs % handling
Steel price ($/ton)
Commodity price
Input cost driving COGS
Container freight ($/FEU)
Freight rate
Niche data a terminal may lack
Import tariff rate
Tariff rate
Regulatory change scraped from announcements
Competitor list price
Competitor price
Scraped from a public pricing page
Revenue growth 8%, buried in =B5*1.08
Internal
Shows embedded-constant detection, correctly skipped as non-market
Outputs: gross margin, EBITDA and a simple 5-year NPV. Fill in the planted values when building the file, and record the current values you fetch so the demo is reproducible if a live fetch fails.
Schedule
Each build block targets what the next Sense Check needs to test. All times PT.
1. 11:50–12:00, v1. Preloaded demo model; input table with LLM labels; one live Bright Data fetch with a drift flag. If parsing isn't wired, show precomputed results from the demo model.
2. 12:00–1:00, Sense Check 1. Validate the pain (see Sense Check plan).
3. 1:00–2:00. Fetch all driver types, unit normalization, source snippets, confirm/edit label UI.
4. 2:00–3:00, mentor hour. Ask Base44 how to call Daytona and Bright Data; keep building.
5. 3:00–4:00, Sense Check 2. Test trust in labels and fetched values.
6. 4:00–6:00. Impact engine and output bridge; apply round 2 feedback. Use the 5:00 mentor hour on the pitch story.
7. 6:00–7:00, Sense Check 3. Full flow on the clock.
8. 7:00–8:00. Freeze features, build the 3 slides, record a backup demo video.
Sense Check plan
Each round answers one question, and each answer becomes a line on the "what we changed" slide.
Round
Question it answers
The 3 questions to ask
1 (12–1)
Is stale assumptions a real pain?
When did you last update a model you built 3+ months ago, and what triggered it? · Which of these flagged inputs would you have checked yourself? · What's missing from this list that you'd worry about?
2 (3–4)
Do they trust the labels and values?
Is any label wrong? · Would you use this fetched value, or check it elsewhere first? · What would you need to see to sign off without re-checking?
3 (6–7)
Does the full flow save real time?
How long would this check take you by hand? · Which flag mattered most? · Would you run this before reusing a model, and how often?
If round 1 testers are mostly bookkeepers who don't build models, switch to the Idea 3 backup in the main tab.
Log after every round: tester role, the exact quote, what you changed and why.
Pitch
Three slides, built from the round logs.
1. The problem nobody sees. A tester quote about reusing an old model, plus the insight: inputs go stale silently, and no tool checks them against the world.
2. How it works, live. Upload, inputs labeled, values fetched with sources, the output bridge ("EBITDA falls $1.2M; here's why"). Run it live; keep the backup video ready.
3. What testers changed. Before/after for 2–3 changes driven by Sense Check quotes, then the roadmap: always-on monitoring across a team's whole model library.
Risks and fallbacks
Risk
Fallback
Base44 can't run Python or reach Daytona
Parse with SheetJS in a Base44 backend function; show the dependency path instead of recalculating
Bright Data returns messy pages
One curated source URL per driver type; show the source snippet so the user verifies the number
LLM mislabels an input
Confidence score plus the confirm/edit step; low-confidence labels need confirmation
Unit or direction mismatch
Explicit normalization rules per driver type, shown in the report ("inverted USD/EUR")
Live fetch fails during judging
Cached values from the last good run, labeled with their timestamp, plus the backup video
Testers don't build models
Pivot to the Idea 3 backup after round 1