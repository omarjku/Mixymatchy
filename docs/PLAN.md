# Product plan (short)

Full plan and the visual overview were shared as PDFs (Second_Look_Team_Plan.pdf, Second_Look_Overview.pdf).
This file is the living version; it includes the team additions agreed on 30.10.2026.

## Pitch
"Other tools summarise the record. Second Eye checks it, for the task in front of you."

## Features
| # | Feature | Owner |
|---|---|---|
| 1 | Ask in one sentence, any role | E2 |
| 2 | Only the facts the task needs | E2 + M1 (`rulebook/roles.json`, `tasks.json`) |
| 3 | Proof for every fact: highlighted sentence + English | E1 + E3 |
| 4 | Blind-Spot Check: facts you'd miss reading only the latest letter ("3 of 11" is computed) | E2 |
| 5 | Contradiction finder, tiered (contradiction vs documentation note), no false alarms | E2 + M2 (`eval/contradictions_gold.json`) |
| 6 | Fact family tree: how a fact travelled across letters, flagged as "possible copy error" | E2 + E3 |
| 7 | Switch doctor, same patient (lens morph) | E3 |
| 8 | Open follow-ups ("nothing recorded after X") + proof bar | E2 + E3 |
| 9 | Smart answers: latest value as of 15.04.2016, change over time (-12 kg), newest medication list overrides older ones | E2 |
| 10 | "Not applicable" (with its evidence) as well as "not documented" | E2 + M1 |

Nice to have: voice input, timeline slider, clarification-letter draft, German/English toggle,
free-text "ask anything" box (Claude with citations + our quote check).

## Rules
- Only document facts on screen; translations, generic names and computed values allowed.
- Every number on screen is computed, never typed in.
- Contradiction tiers: only passages that cannot all be true are counted; typos and case numbers are documentation notes.
  The lymph-node mismatch is decided by M1/M2 and is shown prominently to the surgeon either way.
- Copy-forward wording: "possible copy error", never "copied wrong".
- Rulebook: M1 replaces each `TODO-cite` with a guideline reference; a second person fills `reviewed_by`.
  Guideline references explain why a need is on the list; they never appear as patient facts.
- No vector search: 8 letters fit in one AI call.

## Reliability marks
consistent / conflicting / stale / not documented / not applicable

## Quality gates
- Verifier negative test: injected fake facts must all be dropped (`backend/tests`).
- 15/15 means on the rendered screen for that situation, with a link, not just present in the fact store.
- The LLM situation parser lands early (keyword rules stay as fallback), tested on `eval/unseen_situations.json`.

## Milestones
G0 foundation (this scaffold) -> G1 verified facts -> G2 first screen, >=12/15 -> G3 7/7 contradictions, 0 false alarms
-> G4 family tree, lens morph, proof bar -> G5 15/15 and >=18/20 unseen -> G6 README, video, metrics.

## Never cut
Sentence-level links, the verifier, "not documented", the eval script.
