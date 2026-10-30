# Handoff: Second Eye (AIM Austria hackathon, Track 1)

Everything a new coding session needs to continue. Start a new session with:
> Read docs/HANDOFF.md, README.md, docs/PLAN.md and docs/contracts.md, then continue with "Next steps".

## 1. The challenge (README.md has the full brief)
- Input: a clinician's role + task as free text (a situation's title + description). The app never sees the questions.
- Output: ONE screen with only the facts that task needs. Every fact links to the exact source sentence. Missing needs say "not documented". Contradictions between documents are flagged. Never invent facts. Translations, generic drug names and computed values are allowed.
- Metrics on the 5 situations (cases/situations.md, answers in cases/expected.json): 15/15 correct, 100% traceability, 0 invented facts, >=5 contradictions net of false alarms, slowest load < 10 s. The jury also tests new situations and new roles for the same patient.
- Judging (1/3 each): clinical usefulness, technical quality and AI (does the screen change with role/task, is every fact linked, does AI help), working end to end.
- Submission: video <= 2 min (say what works and what doesn't), public repo **without data/**, README with architecture, metric results.
- Rule: never commit IBM's data (`data/` is gitignored; `*.zip` too).

## 2. Context from the kickoff (not in the README)
- IBM's Cockpit runs on "Medical Linguistic Assets" (MLA), used in City of Vienna hospitals; IBM wants to learn how AI should complement it. Pitch: "We don't replace MLA, we check it, fill its gaps and filter it for the clinician."
- Judges: IBM technical people + medical professionals. "Use AI only where it helps."
- Self-generated synthetic test data is allowed.

## 3. Team and decisions
- Omar (JKU student, repo owner `omarjku`), teammate `syedwajiulhassan715-rgb` (wrote the Second Eye plan, Next.js frontend, FastAPI shell), medical student(s) (rulebook), a tester.
- Product: **Second Eye**, "Other tools summarise the record. Second Eye checks it, for the task in front of you." Plan: docs/PLAN.md (8 features + additions).
- Decided:
  - Deterministic core; LLM optional (understanding unusual wording). Rule-based path must always work.
  - IBM JSON = index only; the documents are the source of truth.
  - Role/task -> needs come from a hand-written rulebook (README allows hard-coding *kinds* of facts). Every row must get a guideline citation (`TODO-cite` placeholders) and a second reviewer. Guidelines decide what to look for, never what to say. No AI processing of NICE text (licence).
  - IPS (International Patient Summary, used by Austria's ELGA patient summary) is pitch framing / vocabulary, not a build requirement.
  - Doctors can flag data as wrong, never edit it.
  - No Snowflake / vector search: 8 letters (~7k tokens) fit in one LLM call.
  - Security: login + 4-digit PIN lock (security/), audit log.
  - Hosting: Hugging Face Docker Space (free, sleeps only after 48 h idle), auto-deployed by GitHub Action.

## 4. What is built (branch `claude/peaceful-ride-nw0xm5`, all pushed)
| Part | Path | Status |
|---|---|---|
| Fact store | `pipeline/` (`python3 -m pipeline.build`) | 359 passages, 254 facts (161 rule, 93 IBM), every quote verified, 0 dropped |
| Compare | `compare/` (`python3 -m compare.build`) | 5 counted contradictions, 3 documentation notes, blind spots (9 of 30 important items missing from the latest letter), open follow-ups, propagation chains |
| Query engine | `engine/` (`python3 -m engine.query --brief "<text>"`) | situation -> role/task -> needs -> answer cards (consistent / conflicting / outdated / not documented / not applicable), ~50 ms |
| Routing KB (default rulebook) | `rulebook/kb/routing_knowledge_base.json` (medical team), `rulebook/slot_map.json` (slot -> fact categories / ICD-10 / ATC), `engine/kb.py` (load + validate, `python3 -m engine.kb`), `engine/route.py`, `engine/kbfill.py`, `engine/test_kb.py` | 63 slots, 18 bundles, 20 roles, rules R01-R20 evaluated on facts, R21 staleness, R22 label panel; `--detail short|long`; `--legacy-rulebook` / `SECOND_LOOK_RULEBOOK=legacy` falls back |
| Legacy rulebook | `rulebook/roles.json`, `tasks.json` (engine), `rulebook/scaffold/` (teammate's originals), `needs.json`, `synonyms.json`, `drugs.json` | 211 rows with `TODO-cite`; kept until KB parity is signed off |
| Eval | `eval/run.py` (strict fact-store scorer), `eval/run_api.py` (HTTP scorer), `eval/answer_keys.json` | 15/15, 0 invariant violations |
| API | `backend/app/main.py` + `adapter.py` (engine -> `schema.py` Briefing) | `SECOND_LOOK_BACKEND=llm` switches to the teammate's LLM store |
| Frontend | `frontend/` (Next.js 15) | builds; static export used in deployment |
| Security | `security/` (`python3 -m security.server`, demo creds in security/README.md) | 24 tests; NOT yet wired into the Next.js app |
| Deploy | `Dockerfile`, `deploy/start.sh`, `deploy/hf/README.md`, `.github/workflows/deploy-hf.yml` | site password gate (`SITE_USER`/`SITE_PASSWORD`), data from secret `DATA_ZIP_B64` |
| Contracts | `docs/contracts.md` | data formats for data/build/* |

Counted contradictions: carotid stenosis side (12340012 duplex paragraph says right, everything else left), BMI 2015 (78 kg/170 cm = 27.0 vs 29.4), BMI 04/2016 (67/171 = 22.9 vs 29), 2016 admission (10.04 vs 12.04), biopsy (11.04 vs 12.04). Notes: case number, right axillary nodes vs none on ultrasound, date typo "20156". Suppressed false alarms: height 170/171, admission BP 140/90 vs 145/90, weight trend, Blopress 1-0-1/2 -> 1-0-1, anything differing only from IBM JSON.

## 5. Run locally
```bash
pip install -r backend/requirements.txt && (cd frontend && npm ci)
# put the organisers' data in data/ (unzip track1-data.zip at repo root -> data/patient-0000-0001/...)
make build          # pipeline + compare
make test           # all unit tests
python3 -m eval.run --strict
make backend        # http://127.0.0.1:8000
make frontend       # http://localhost:3000
```

## 6. Deployment (Hugging Face Space), steps still to do
1. huggingface.co/new-space: name `second-look`, SDK Docker (blank), CPU basic, public (the app is password-gated).
2. Space secrets: `DATA_ZIP_B64` (= `base64 -w0 track1-data.zip`), `SITE_USER`, `SITE_PASSWORD` (Omar has the current values; never commit them).
3. HF write token -> GitHub repo secret `HF_TOKEN`; GitHub repo variable `HF_SPACE` = `<hf-user>/second-look`.
4. GitHub Actions -> "Deploy to Hugging Face Space" -> Run workflow. Then every push to `main` or `claude/peaceful-ride-nw0xm5` redeploys.
5. URL: `https://<hf-user>-second-look.hf.space`.
- With the HF CLI available locally you can also push directly: `huggingface-cli login`, then follow the workflow's commands.
- A Render service also exists (`second-look`, srv-dbht95mk1f9s73e5qjh0, Frankfurt, free, auto-deploys the branch) without `DATA_ZIP_B64`, so it crashes on start. Delete it or add the variable.

## 7. Git state and gotchas
- Work branch: `claude/peaceful-ride-nw0xm5`. It merges the teammate's `main` (force-pushed twice; last one recorded with a no-op merge). Ask the team not to force-push `main`.
- Draft PR not yet opened (GitHub API failed): https://github.com/omarjku/Mixymatchy/compare/main...claude/peaceful-ride-nw0xm5
- Never commit `data/`, `track1-data.zip`, `.env`, the data base64, or real passwords.
- A GitHub token was pasted in an earlier chat; make sure it was revoked.

## 8. Next steps (priority order)
1. Finish HF deployment (section 6) and give the tester the URL.
2. Screen polish: collapse "not documented" should-items into one line, merge duplicate cards (allergy shown 3x), latest plan only in the planned-procedure card.
3. Filter blind spots and open follow-ups to the current task (currently patient-wide).
4. Wire `security/` (PIN lock + audit) into the Next.js app (see security/README.md).
5. Medical student: replace `TODO-cite` in rulebook with guideline citations, review must/should, merge `rulebook/scaffold/` ideas; second reviewer signs off.
6. Optional LLM layer (`SECOND_LOOK_LLM=1`, ANTHROPIC_API_KEY): role/task understanding for unusual wording, choosing only from rulebook IDs; fallback to rules on timeout (4 s) or invalid output.
7. Test 8–10 unseen situations (pharmacist, oncologist, vascular surgeon, radiologist, cardiologist, nurse, GP prostate exam -> not applicable, endocrinologist) and review screens with the medical team.
8. Submission: README metrics table (ours vs MLA-only baseline), "where we use AI and why" table, 2-minute video, repo made public **after** confirming no data in history.
9. Ideas kept for later: voice input (browser speech API), weight/BMI trend chart, print/PDF, German/English toggle, "flag as wrong" annotations, IPS export.
