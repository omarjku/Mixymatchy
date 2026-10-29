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
              with stable IDs (12340012:s041)                (knowledge/roles.yaml, triggers.yaml)
  extract.py  Claude extracts facts that cite                select verified facts per need
              segment IDs only                               missing need -> "not documented"
  verify.py   code checks each value is in its               attach findings for those needs
              cited segment, drops the rest
  rules.py    deterministic conflict rules           frontend/ (Next.js)
  store.py    -> cache/*.json (git-ignored)            briefing + source pane with highlighted passage
```

| Component | Tech | Role |
|---|---|---|
| Frontend | Next.js 15, React 19, Tailwind 4 | Input, briefing, source viewer |
| Backend | Python, FastAPI | Fact store, rules, briefing API |
| AI | Claude Opus (extraction, offline), Claude Haiku (situation parsing, online) | Reads German letters, understands the request |
| Knowledge | `knowledge/*.yaml` | What each role needs, drug names, synonyms, task triggers |
| Eval | `eval/run.py` | Scores the 15 questions, traceability, latency |

### Status of the scaffold

| Part | Status |
|---|---|
| Ingest + segmentation with stable IDs and exact offsets | working |
| BMI conflict rule | working (finds both BMI contradictions) |
| Fact verifier | working |
| Briefing API + role keyword parser + "not documented" | working (all needs empty until extraction exists) |
| Frontend: input, role chips, briefing, source pane with highlight | working |
| Claude extraction + sceptic pass | TODO (E1) `backend/app/extract.py` |
| More conflict rules, blind spot, families, follow-ups, trust marks | TODO (E2) `backend/app/rules.py`, `query.py` |
| LLM situation parser | TODO (E2) `backend/app/query.py` |
| Eval answer keys, contradiction scoring, unseen situations | TODO (M2/E2) `eval/` |

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

# 4. evaluation (backend running)
python eval/run.py
```

With `make`: `make install`, `make precompute`, `make backend`, `make frontend`, `make eval`.

## Repository layout

```
backend/app/    ingest, extract, verify, rules, query, store, schema, main (API), precompute
knowledge/      needs.yaml, roles.yaml, triggers.yaml, drugs.yaml, synonyms.yaml   (clinicians own the content)
frontend/       Next.js app (app/page.tsx, components/SourcePane.tsx, lib/api.ts)
eval/           run.py, contradictions_gold.json, unseen_situations.json
cases/          the 5 situations and expected answers from the organisers
docs/           challenge brief and product plan
```

## Rules we follow

- Only facts from the documents appear on screen. Translations, generic drug names and calculated values are allowed.
- The model cites segment IDs; it never writes the text shown as evidence. Unverifiable facts are dropped.
- "Not documented" is decided by code, not by the model.
- Guidelines may shape `knowledge/` (what to look for), never what is shown as a fact.
- `data/`, `cache/` and `.env` are never committed.
