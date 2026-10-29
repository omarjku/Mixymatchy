# Second Look

**The right patient facts for every doctor's task, and a warning when the record is wrong.**

A clinician types who they are and what they are doing ("Anaesthetist, pre-op check before breast surgery").
Second Look returns one screen with:

1. the facts that task needs, each linked to the exact sentence in the original letter,
2. "not documented" where the letters are silent,
3. what the record gets wrong: contradictions, facts the latest letter forgot, open follow-ups.

Built for Track 1 (Clinical Documentation). The challenge brief is in [docs/CHALLENGE.md](docs/CHALLENGE.md),
the product plan in [docs/PLAN.md](docs/PLAN.md).

> The IBM patient data is **not** in this repository (challenge rule). See *Setup*.

## Architecture

Two halves meet at one contract, `backend/app/schema.py` (mirrored by `frontend/lib/api.ts`).
The default path is fully deterministic and needs no API key; the LLM is optional.

```
OFFLINE (once per patient, python3)              ONLINE (per request, ~20 ms)
pipeline/   python3 -m pipeline.build              backend/app/main.py   FastAPI: /health, /documents,
  documents -> display text -> passages              /documents/{id}, /segments/{id}, POST /briefing
  (exact offsets, 12340012:p0042)                  backend/app/adapter.py
  rules + IBM hints -> facts that quote their        engine.screen.build_screen(situation)
  passage word for word                                engine/understand.py  role + tasks (rulebook/
  -> data/build/{docs,passages,facts}.json               roles.json, tasks.json; optional Haiku hint)
compare/    python3 -m compare.build                   engine/fill.py  one card per need: latest as of,
  contradictions, tiered: contradiction vs               newest medication list wins, series change,
  documentation note; blind spots vs latest              "nothing recorded after", not documented /
  letter; open follow-ups -> compare.json                not applicable (with evidence)
                                                       engine/data.py  re-verifies every fact at load
Both are run automatically by the backend          -> mapped to schema.Briefing (facts, superseded,
on first start if data/build/ is missing.             computed, findings, blind spot, stats counted
                                                      from the briefing itself)
                                                 frontend/ (Next.js): briefing + source pane
```

Mapping engine -> contract (details in `backend/app/adapter.py`): passages become `Segment`s, each card
becomes a `NeedResult`, each displayed item a `Fact` (one per statement, with the segments of every letter
that repeats it); card status `conflicting`/`outdated` becomes `Fact.trust` `conflicting`/`stale`; older
values (e.g. a dose from an older medication list) go to `superseded`; compare contradictions, blind spots and
open follow-ups become `Finding`s (`conflict`, `dropped`, `followup`; an unstated computed change is `silence`).

| Component | Tech | Role |
|---|---|---|
| Frontend | Next.js 15, React 19, Tailwind 4 | Input, briefing, source viewer |
| Backend | Python, FastAPI | Serves the engine's results in the schema.py contract |
| Offline build | `pipeline/`, `compare/` (stdlib Python) | Passages, verified facts, contradictions, blind spots, follow-ups |
| Engine | `engine/` (stdlib Python) | Situation -> role/tasks -> one card per need |
| AI (optional) | Claude Haiku for situation parsing (`SECOND_LOOK_LLM=1`); Claude extraction in `backend/app/extract.py` (`SECOND_LOOK_BACKEND=llm`) | Proposes a reading of the request; never produces facts or "not documented" |
| Rulebook | `rulebook/roles.json`, `tasks.json` (engine); `rulebook/scaffold/` (original keyword rulebook for the LLM path) | What each role and task needs |
| Eval + tests | `eval/`, `engine/test_engine.py`, `compare/test_compare.py`, `backend/tests/` | 15 questions, traceability, contradictions, latency |

### Status

| Part | Status |
|---|---|
| Passages with exact offsets, facts that quote their passage, load-time re-verification | working (`pipeline/`, `engine/data.py`) |
| Contradictions (5 counted) and documentation notes (3), blind spot (9 of 30), open follow-ups (2 of 8) | working (`compare/`) |
| Role/task understanding, cards per need, smart answers, not documented vs not applicable | working (`engine/`), 8 unseen situations tested |
| FastAPI serving the engine in the schema.py contract | working (`backend/app/adapter.py`), 15/15 answers over HTTP, ~20 ms median |
| Frontend on the merged API | working, unchanged |
| LLM path: Claude extraction + verifier into `cache/` | kept, off by default (`SECOND_LOOK_BACKEND=llm`); extraction is still a stub |
| Superseded values and computed values shown in full in the UI | partly: the UI shows a count + source link for superseded values |
| Guideline citations in the rulebook (`TODO-cite`) + second reviewer | TODO (M1, M2) `rulebook/` |

## Setup

Requirements: Python 3.11+, Node 20+. An Anthropic API key is optional.

```bash
# 1. data: copy the organisers' data folder into the repo root (it is git-ignored)
#    -> data/patient-0000-0001/...

# 2. offline build (optional: the backend does this on first start if data/build/ is missing)
python3 -m pipeline.build          # -> data/build/docs.json, passages.json, facts.json
python3 -m compare.build           # -> data/build/compare.json
python3 -m engine.query --brief "Anaesthetist, pre-op check"   # the engine on the command line

# 3. backend (from the repo root; engine/, pipeline/, compare/ are imported from there)
pip install -r backend/requirements.txt
uvicorn --app-dir backend app.main:app --port 8000
#   or: cd backend && uvicorn app.main:app --reload --port 8000
#   SECOND_LOOK_LLM=1 + ANTHROPIC_API_KEY: Haiku proposes the role/tasks (validated against the rulebook)
#   SECOND_LOOK_BACKEND=llm: the teammate's LLM-extracted store (cd backend && python -m app.precompute)

# 4. frontend (new terminal)
cd frontend
npm install
npm run dev                      # http://localhost:3000

# 5. tests and evaluation (from the repo root)
python3 -m unittest engine.test_engine compare.test_compare eval.test_eval
cd backend && python3 -m pytest -q && cd ..   # adapter + LLM-path unit tests
python3 -m eval.run                           # offline eval -> data/build/eval_report.md
python3 -m eval.run_api                       # HTTP eval against the running backend (15 questions, latency)
```

With `make`: `make install`, `make build`, `make backend`, `make frontend`, `make test`, `make eval`.

## Repository layout

```
pipeline/       offline: documents -> passages -> verified facts (data/build/)
compare/        offline: contradictions, blind spots, open follow-ups (data/build/compare.json)
engine/         online: situation -> role/tasks -> cards (CLI: python3 -m engine.query)
backend/app/    FastAPI: main (API), adapter (engine -> schema), schema (the contract), store;
                LLM path: ingest, extract, verify, rules, query, precompute
backend/tests/  adapter tests (5 situations, 15 answers, links, stats) + LLM-path unit tests
rulebook/       roles.json, tasks.json (engine), needs.json, drugs.json, synonyms.json, scaffold/
frontend/       Next.js app (app/page.tsx, components/SourcePane.tsx, lib/api.ts)
eval/           core.py, answer_keys.json, run.py (offline), run_api.py (HTTP), contradictions_gold.json
cases/          the 5 situations and expected answers from the organisers
docs/           challenge brief, product plan, data contracts
```

## Rules we follow

- Only facts from the documents appear on screen. Translations, generic drug names and calculated values are allowed.
- Every fact quotes its passage word for word and is re-checked at load; unverifiable facts are dropped. An LLM may only propose a reading of the request.
- "Not documented" is decided by code, not by the model.
- Guidelines may shape `rulebook/` (what to look for, cited as `evidence`), never what is shown as a fact.
- Every number on screen (counts, blind spot "3 of 11", weight change) is computed, never typed in.
- Contradictions are tiered: only passages that cannot all be true count; typos and case numbers are documentation notes.
- Copy-forward findings say "possible copy error", never "copied wrong".
- `data/`, `cache/` and `.env` are never committed.
