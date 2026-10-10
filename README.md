# Since

Financial models are built on hardcoded assumptions — interest rates, FX, commodity prices, freight, tariffs — that were right the day the model was built and drift after. Upload an Excel model and Since finds every hardcoded assumption (including numbers buried inside formulas), labels the real-world driver it stands for, checks it against today's data and recent news, and shows which ones have gone stale, by how much, and what that does to the outputs.

Built for FP&A analysts and anyone reviewing many models at once.

## Layout

| Path | What | Owner |
|---|---|---|
| `schema/` | The shared contract. `constant.schema.json` + `fixtures/case_study.json`. Change only by team agreement, schema and fixture in the same commit. | team |
| `data/` | Case-study workbook and its ground truth | Matthew |
| `engine/graph/` | Parse xlsx, dependency graph, constant detection, impact recalculation | modeling |
| `engine/checks/` | Labeling, driver catalog, FRED series, Bright Data news, Jev | checks |
| `web/` | Vite + React front end | Aiden |

## Run

```sh
cp .env.example .env

# engine
cd engine && python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app:app --reload        # http://localhost:8000
pytest

# web
cd web && npm install && npm run dev   # http://localhost:5173
```

`VITE_USE_FIXTURE=1` makes the web app read `schema/fixtures/case_study.json` instead of calling the engine.

## Rules

- No generated prose on screen: numbers, cell refs, quotes, sources, stamps.
- Every value comes from the workbook or a cited source. Nothing is invented.
- `main` always runs. One branch per person, merge often.
