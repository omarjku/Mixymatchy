# Second Look

**Other tools summarise the record. Second Look checks it, for the task in front of you.**

Built for the AIM Austria hackathon, Track 1 (Clinical Documentation). The challenge brief is in [docs/CHALLENGE.md](docs/CHALLENGE.md).

> **The IBM patient data is not in this repository** (challenge rule). `data/`, `data/build/`, `cache/` and `*.zip` are git-ignored. See [Run it locally](#run-it-locally).

## What it does

A clinician types who they are and what they are about to do, for example *"Anaesthetist, pre-operative check before breast surgery"*. Second Look returns one screen with:

- **the facts that task needs**, each linked to the exact sentence or table row in the original German letter it comes from;
- **"not documented"** (with what was searched) or **"not applicable"** (with its evidence) where the letters are silent;
- **where the record is wrong or incomplete**: contradictions between passages, facts the latest letter dropped, and recommended follow-ups with no later record.

*Screenshot: added at submission time from the demo build. Screenshots of real screens are not committed because they contain document text.*

## Architecture

Two phases. An offline build reads the eight letters once and freezes a verified fact store. Every request then only looks things up, so a screen takes milliseconds, not seconds.

```
OFFLINE (make build, once)                                 ONLINE (per request)

data/patient-0000-0001/   8 German letters (git-ignored)
        │
        ▼
pipeline/   passages with stable IDs and offsets            POST /briefing {situation, detail}
            rule extractors + IBM index linker                      │
            every quote checked against its passage                 ▼
        │                                                    engine/   understand: role + task (alias matcher,
        ▼                                                              optional LLM proposal, IDs validated)
compare/    contradictions (tiered), blind spots,                     route: bundles → slots by priority P1–P3
            open follow-ups, propagation chains                       fill: latest value as of the latest letter,
        │                                                              computed values, not documented / not
        ▼                                                              applicable, link rules, guideline badges
data/build/  docs, passages, facts, compare (git-ignored)           │
                                                                    ▼
rulebook/kb/  routing knowledge base (roles, bundles,       backend/app/  FastAPI: adapter → Briefing schema,
              slots, rules, guidelines; no patient facts)                 /documents, /segments, site password gate
                                                                    │
                                                                    ▼
                                                            mobile/   phone-first web app: facts with sources,
                                                                      contradictions, open items, source sheet
```

| Component | Path | What it does | Tech |
|---|---|---|---|
| Fact store | `pipeline/` | Splits each letter into passages with stable IDs and character offsets, extracts typed facts (medication, allergy, measurement, finding, plan…), links IBM's extraction as an index only, and rejects any fact whose quote is not verbatim in its passage. | Python (standard library) |
| Compare | `compare/` | Finds contradictions with deterministic checks (BMI recomputation, event dates, laterality, …), separates counted contradictions from documentation notes, finds facts missing from the latest letter and follow-ups with no later record. | Python |
| Routing knowledge base | `rulebook/kb/` *(on branch `claude/peaceful-ride-nw0xm5` until merged)* | Written by the medical team: 20 roles, 18 task bundles, 63 fact slots with priorities P1–P3, link rules, consistency checks, guideline and drug-label sources. Holds no patient facts. | JSON + review PDF |
| Legacy rulebook | `rulebook/roles.json`, `rulebook/tasks.json` | The earlier hand-written role → needs table. Default on `main` until the knowledge base is merged; then available with `SECOND_LOOK_RULEBOOK=legacy`. | JSON |
| Query engine | `engine/` | Situation text → role and task → needs → answer cards (consistent, conflicting, outdated, not documented, not applicable). `--detail short` shows P1 only. | Python |
| API | `backend/app/` | FastAPI. `adapter.py` maps engine screens to the `Briefing` schema in `schema.py`; serves documents and passages for the source view; optional site password. | FastAPI, Pydantic |
| Mobile app | `mobile/` | The demo frontend. Calls the API (`src/lib/backend.ts`), shows facts with their source passages, contradictions, documentation notes and open items. Works on a phone. | React 19, Vite, Tailwind 4, Motion |
| Access security | `security/` | Sign-in, PIN lock, idle lock, tamper-evident audit log. Not yet wired into the mobile app. | Python (standard library), plain JS |
| Evaluation | `eval/` | Scores the 15 expected answers on the fact store and over HTTP, checks invariants (quotes verbatim, numbers in quotes). | Python |
| Reference frontend | `frontend/` | First Next.js frontend; superseded by `mobile/`. The Docker image still builds it (see Limitations). | Next.js 15 |

The data contracts for `data/build/` are in [docs/contracts.md](docs/contracts.md); the API contract and how the app maps it are in [docs/INTEGRATION.md](docs/INTEGRATION.md).

## Where AI is used, and where it is not

The core is deterministic, so every screen can be reproduced and checked.

| Step | How | Why |
|---|---|---|
| Extracting facts | Rules plus IBM's extraction as an index; every quote validated in code | Eight short letters; rules are checkable and fast |
| Understanding the request | Alias and tag matcher in code. **Optional:** Claude proposes a role and task IDs (`engine/llm.py`, enabled with `SECOND_LOOK_LLM=1` and `ANTHROPIC_API_KEY`; model from `SECOND_LOOK_LLM_MODEL`, default `claude-haiku-4-5`) | Unusual wording and unseen roles. The proposal is untrusted: only IDs that exist in the rulebook are kept, and the matcher is the fallback on timeout (4 s) or invalid output |
| Deciding what to show, "not documented", contradictions, calculations | Code only | The model never writes patient facts, statuses, verdicts or numbers |
| LLM extraction path | `backend/app/extract.py`, `SECOND_LOOK_BACKEND=llm` | Experimental alternative store; the model may cite passage IDs only and a verifier drops anything it cannot find |

No guideline text is processed by a model (licence). Guidelines in the knowledge base only explain why a fact is on a checklist; they are never shown as patient facts.

## What the screen guarantees

- **Every fact is quoted and linked.** A fact without a verbatim quote in a known passage is dropped at build time.
- **Missing is explicit.** A need with no fact shows "not documented", decided by code, never by a model.
- **Computed values show their inputs.** Age, weight change and BMI recomputation link every passage they use. Translations and generic drug names are the only other changes to document text.
- **Contradictions are tiered.** Only passages that cannot all be true are counted; typos, case numbers and findings that a method or date difference can explain are shown as documentation notes. Changes over time, small measurement differences and differences from IBM's JSON are not flagged.
- **"As of" is the latest letter** (15 April 2016), so "current medication" means the newest medication list.
- **Read only.** The app never edits the record.

## Run it locally

Requirements: Python 3.11+, Node 20+. An Anthropic API key only for the optional LLM parser.

```bash
# 1. Data: unzip the organisers' data at the repo root -> data/patient-0000-0001/...
# 2. Python dependencies
pip install -r backend/requirements.txt

# 3. Build the fact store and contradictions (writes data/build/)
make build

# 4. API on http://127.0.0.1:8000
make backend

# 5. Mobile app on http://localhost:5173 (new terminal)
cd mobile && npm ci && npm run dev
```

The Vite dev server proxies `/briefing`, `/documents`, `/segments` and `/health` to the API (`BACKEND_URL`, default `http://127.0.0.1:8000`), so the app also works from a phone on the same network. `VITE_MOCK=1` runs the app on invented mock data without a backend.

Optional switches:

| Variable | Effect |
|---|---|
| `SECOND_LOOK_LLM=1` + `ANTHROPIC_API_KEY` | Claude proposes role/task IDs for unusual wording |
| `SECOND_LOOK_RULEBOOK=legacy` | Use `rulebook/roles.json` instead of the knowledge base (after the knowledge base is merged) |
| `SECOND_LOOK_BACKEND=llm` | Experimental LLM-extracted store (`make precompute` first) |
| `SITE_USER`, `SITE_PASSWORD` | Basic-auth gate on every route except `/health` |

Command line, without the app:

```bash
python3 -m engine.query "Anaesthetist, pre-operative check before breast surgery" --brief
```

### Tests and evaluation

```bash
make test                         # engine, compare and eval unit tests + backend tests
python3 -m eval.run --strict      # 15 expected answers on the fact store; exit 1 unless 15/15 and 0 violations
python3 -m eval.run_api           # same 15 answers over HTTP, with latency (API running)
python3 -m unittest security.test_security
```

Measured results are in [docs/SUBMISSION.md](docs/SUBMISSION.md).

## Deployment

*(On branch `claude/peaceful-ride-nw0xm5` until merged.)* One Docker container: FastAPI serves the API and the built frontend from the same origin. The patient data never enters git or the image: `deploy/start.sh` unpacks it at start-up from the secret `DATA_ZIP_B64`. `SITE_USER` / `SITE_PASSWORD` protect every route. `.github/workflows/deploy-hf.yml` mirrors the repository to a Hugging Face Docker Space on every push; the Space holds the three secrets.

## Repository layout

```
pipeline/     fact store build (passages, extractors, IBM linker)
compare/      contradictions, blind spots, follow-ups
engine/       understand → route → fill; optional LLM hook (llm.py)
rulebook/     routing knowledge base (kb/, after merge) and legacy role/task tables
backend/      FastAPI app (app/), tests
mobile/       demo frontend (React + Vite)
frontend/     earlier Next.js frontend (reference)
security/     sign-in, PIN lock, audit log
eval/         scorers, answer keys, contradiction gold list, unseen situations
cases/        the organisers' five situations and expected answers
deploy/       container entrypoint, Hugging Face Space config
docs/         challenge brief, plan, contracts, integration, frontend plan, submission
```

## Limitations

- **Two rulebooks until the merge.** `main` still runs the legacy rulebook, which ignores `detail: short`, so screens are long (up to ~120 facts for some roles). With the routing knowledge base, short mode shows the P1 facts only (about 20).
- **Routing gaps without the LLM parser:** "dietitian reviewing her weight" and "GP checking her HbA1c" fall back to the general summary, and "rheumatologist" is not one of the 20 roles. The LLM parser is off by default.
- **Diagnoses are not merged across letters**, so a general summary lists every mention (the app shortens lists over 20 entries).
- **Mixed languages.** The app's interface is German; facts and explanations from the backend are English. An English default interface is in progress.
- **Some explanations show internal detail** (search categories and check IDs).
- **The Docker image builds `frontend/`, not `mobile/`**, until the deployment is switched.
- **The PIN lock is not yet wired into the mobile app.**
- **Guideline citations are partly placeholders** (`TODO-cite`); the knowledge base has not had a full clinician review.

## Team

Built by a team of developers and clinicians: backend and evaluation, mobile frontend, product plan and integration, and a medical team that wrote and reviews the routing knowledge base.

## Licence and data

Code: no licence file yet (add one before the repository is made public). Patient data: synthetic data provided by IBM Austria for the hackathon, not redistributed here. Guidelines are referenced by title and link only; no guideline text is reproduced or processed by a model.
