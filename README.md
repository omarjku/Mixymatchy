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

```
OFFLINE (once per patient)                      ONLINE (per request, target 2-4 s)
backend/app/precompute.py                        backend/app/main.py  POST /briefing
  ingest.py   normalise + split into segments      query.py  parse situation -> role + needs
              with stable IDs (12340012:s041)                (rulebook/roles.json, tasks.json)
  extract.py  Claude extracts facts that cite                select verified facts per need
              segment IDs only                               smart answers: latest as of date, newest
  verify.py   code checks each value is in its                 medication list wins, computed change,
              cited segment, drops the rest                    "nothing recorded after X"
  rules.py    deterministic conflict rules,                  "not documented" / "not applicable"
              tiered: contradiction vs note                  blind spot vs latest letter, findings
  store.py    -> cache/*.json (git-ignored)                  stats computed from the screen
                                                 frontend/ (Next.js): briefing + source pane
```

| Component | Tech | Role |
|---|---|---|
| Frontend | Next.js 15, React 19, Tailwind 4 | Input, briefing, source viewer |
| Backend | Python, FastAPI | Fact store, rules, briefing API |
| AI | Claude Opus (extraction, offline), Claude Haiku (situation parsing, online) | Reads German letters, understands the request |
| Rulebook | `rulebook/*.json` | What each role and task needs (with guideline citation + reviewer), drug names, synonyms |
| Eval + tests | `eval/run.py`, `backend/tests/` | Scores the 15 questions, traceability, latency; unit tests for the guarantees |

### Status of the scaffold

| Part | Status |
|---|---|
| Ingest + segmentation with stable IDs and exact offsets | working |
| BMI conflict rule (tier: contradiction) | working (finds both BMI contradictions) |
| Fact verifier | working; negative test drops 5/5 invented facts |
| Smart answers: latest as of 15.04.2016, newest medication list overrides, computed weight change, "nothing recorded after" | working, unit-tested on fixtures |
| "Not documented" vs "not applicable" (with evidence) | working, unit-tested |
| Blind spot vs latest letter, stats computed from the screen | working, unit-tested |
| Briefing API + role keyword parser | working (real data shows "not documented" until extraction exists) |
| Frontend: input, role chips, briefing, computed values, contradiction tiers, multi-letter source pane | working |
| Claude extraction + sceptic pass | TODO (E1) `backend/app/extract.py` |
| More conflict rules (dates, laterality, findings), fact families, trust marks | TODO (E2) `backend/app/rules.py`, `query.py` |
| LLM situation parser | TODO (E2) `backend/app/query.py` |
| Eval answer keys, contradiction scoring, unseen situations | TODO (M2/E2) `eval/` |
| Guideline citations in the rulebook (`TODO-cite`) + second reviewer | TODO (M1, M2) `rulebook/` |

## Setup

Requirements: Python 3.11+, Node 20+, an Anthropic API key.

```bash
# 1. data: copy the organisers' data folder into the repo root (it is git-ignored)
#    -> data/patient-0000-0001/...
cp .env.example .env            # add ANTHROPIC_API_KEY

# 2. backend
cd backend
pip install -r requirements.txt
python -m app.precompute --skip-llm   # builds cache/ (drop --skip-llm once extraction is implemented)
uvicorn app.main:app --reload --port 8000

# 3. frontend (new terminal)
cd frontend
npm install
npm run dev                      # http://localhost:3000

# 4. tests and evaluation
cd backend && python -m pytest -q   # unit tests (no API key needed)
python eval/run.py                  # from repo root, backend running
```

With `make`: `make install`, `make precompute`, `make backend`, `make frontend`, `make test`, `make eval`.

## Repository layout

```
backend/app/    ingest, extract, verify, rules, query, store, schema, main (API), precompute
backend/tests/  unit tests for the guarantees (verifier, smart answers, not applicable, blind spot, stats)
rulebook/       needs.json, roles.json, tasks.json, drugs.json, synonyms.json   (clinicians own the content)
frontend/       Next.js app (app/page.tsx, components/SourcePane.tsx, lib/api.ts)
eval/           run.py, contradictions_gold.json, unseen_situations.json
cases/          the 5 situations and expected answers from the organisers
docs/           challenge brief and product plan
```

## Rules we follow

- Only facts from the documents appear on screen. Translations, generic drug names and calculated values are allowed.
- The model cites segment IDs; it never writes the text shown as evidence. Unverifiable facts are dropped.
- "Not documented" is decided by code, not by the model.
- Guidelines may shape `rulebook/` (what to look for, cited as `evidence`), never what is shown as a fact.
- Every number on screen (counts, blind spot "3 of 11", weight change) is computed, never typed in.
- Contradictions are tiered: only passages that cannot all be true count; typos and case numbers are documentation notes.
- Copy-forward findings say "possible copy error", never "copied wrong".
- `data/`, `cache/` and `.env` are never committed.
