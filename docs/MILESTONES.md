# Milestones to submission

Plan: docs/PLAN.md (G5 15/15 + unseen, G6 README, video, metrics). Submission steps: docs/SUBMISSION.md §5.
Tick a box in the same PR that finishes it.

## How we avoid conflicts

1. **One owner per area.** Change another owner's files only in a PR that names them for review.

   | Area | Files | Owner |
   |---|---|---|
   | Gate, LLM call, branding, deploy | `engine/clinical.py`, `engine/intent.py`, `engine/llm*.py`, `rulebook/clinical_roles.json`, `rulebook/task_intent.json`, `Dockerfile`, Render | Omar |
   | Mobile app | `mobile/` | Zoha |
   | Questions, screen text, key facts, topics | `engine/ask.py`, `engine/fill.py`, `engine/keyfacts.py`, `engine/focus.py`, `rulebook/ask_lexicon.json`, `rulebook/kb_overlay.json` (`role_topics`, `task_focus_scope`), `eval/paraphrase/` | Syed |
   | Shared, so keep the change small and say so in the PR | `engine/screen.py`, `engine/route.py`, `docs/DECISIONS.md`, `Makefile` | everyone |

2. **One branch per milestone, always from fresh `origin/main`.** Before opening the PR, merge `origin/main` into the branch again and re-run the checks. Never work on two local copies of the same branch.
3. **Small PRs, merged quickly.** One milestone per PR, so no branch stays open long enough to drift.
4. **Checks before every PR:** `make test`, `python -m eval.run` (15/15), `python -m eval.keyfacts` (15/15, at most 8 lines), `python -m eval.redteam.run` (leaks not above main).
5. **No more Makefile conflicts.** The `test` line lists every test module, so every branch edits that one line. M4 replaces it with discovery.

## Checklist

- [ ] **M1: Merge PR #11** (trustworthy screen text, fewer false refusals, new situations 125 → 136/234). Mergeable. Omar reviews the `engine/clinical.py` and `rulebook/clinical_roles.json` changes.
- [ ] **M2: AI reads the question** (`feat/ai-questions`). The one LLM call also returns `answer_slots` and German `question_terms`; the screen still shows only record facts, verbatim passages or "Nothing found". Adds a paraphrase eval: the 15 official questions worded 5 ways each. Omar reviews: it touches `engine/llm.py` and one gate condition in `engine/screen.py`. After deploy, test on Render with the key set.
- [ ] **M3: Statistics from statistics-worth-displaying.pdf.** Candesartan as a daily total (24 → 32 mg/day, +33%); recorded BMI against calculated BMI per letter; blood pressure day against night (140/88 → 128/80). Each change links both of its inputs. Owner: Syed.
- [ ] **M4: Test discovery.** `make test` runs `python3 -m unittest discover -s engine -p "test_*.py"` plus the compare and eval tests, so no one edits the test line again. Owner: Omar (Makefile), agreed first.
- [ ] **M5: In-app proof.** Playwright check in `mobile/e2e/`: each official situation typed, every expected answer visible without a click. Plus a test that clicks every source link and checks the passage. Owner: Zoha (mobile) + Syed (expected answers).
- [ ] **M6: Clinician review.** One clinician reads the 5 screens and confirms 0 invented facts; record it in SUBMISSION.md. Owner: team.
- [ ] **M7: Freeze and submit** (SUBMISSION.md §5). No data or zip in git history; fresh clone works; metrics table re-run on `main`; `git tag demo-v1`; Render URL works; README limitations match; video ≤ 2:00 recorded from `demo-v1`; repository made public last.

## Waiting on someone else

- Holdout failures that need bundle changes (dentist, physio, medical oncologist, ophthalmologist, surgeon "not documented" cards; B08 handover without the planned operation): medical team.
- The 5 red-team false blocks are requests without a role. By owner policy (DECISIONS 19) they get no data; change only if the owner decides to.
