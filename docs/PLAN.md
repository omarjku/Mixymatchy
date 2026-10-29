# Product plan (short)

Full plan and the visual overview were shared as PDFs (Second_Look_Team_Plan.pdf, Second_Look_Overview.pdf).

## Pitch
"Other tools summarise the record. Second Look checks it, for the task in front of you."

## Features
| # | Feature | Owner |
|---|---|---|
| 1 | Ask in one sentence, any role | E2 |
| 2 | Only the facts the task needs | E2 + M1 (`knowledge/roles.yaml`) |
| 3 | Proof for every fact: highlighted sentence + English | E1 + E3 |
| 4 | Blind-Spot Check: facts you'd miss reading only the latest letter | E2 |
| 5 | Contradiction finder, no false alarms | E2 + M2 (`eval/contradictions_gold.json`) |
| 6 | Fact family tree: how an error spread across letters | E2 + E3 |
| 7 | Switch doctor, same patient (lens morph) | E3 |
| 8 | Open follow-ups + proof bar ("23 facts, 23 verified, 0 dropped") | E2 + E3 |

Nice to have: voice input, timeline slider, clarification-letter draft, German/English toggle.

## Reliability marks
consistent / conflicting / stale / not documented

## Milestones
G0 foundation (this scaffold) -> G1 verified facts -> G2 first screen, >=12/15 -> G3 7/7 contradictions, 0 false alarms
-> G4 family tree, lens morph, proof bar -> G5 15/15 and >=18/20 unseen -> G6 README, video, metrics.

## Never cut
Sentence-level links, the verifier, "not documented", the eval script.
