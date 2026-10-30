# Submission: metrics, video, checklist

Measured on 30 October 2026 on a local machine (Windows, Python 3.13, Node 24). Re-run every number on the `demo-v1` tag before submitting and replace this table if anything changed.

## 1. Metrics on the five situations

| Metric (docs/CHALLENGE.md) | Target | Result | How it was measured |
|---|---|---|---|
| Correct answers | 15 / 15 | **15 / 15** | Fact store: `python3 -m eval.run --strict`. Over HTTP: `python3 -m eval.run_api`. Both detail modes with the routing knowledge base: 15/15 short, 15/15 long. |
| Correct answers on screen | visible without clicking, with a link | **5 / 5 situations** | Playwright: each situation typed into the mobile app; every expected answer's key tokens found in the rendered results without any click (script in §3). |
| Traceability | 100 % | **100 % by construction** | Every displayed fact carries passage IDs; `eval.run --strict` reports 0 invariant violations (each quote is a verbatim substring of its passage, every number in a value appears in its quote). The source sheet shows the cited passage text from `/documents/{id}`. A click-every-link test is still to be added. |
| Invented facts | 0 | **0** | Same invariant check: no fact without a verbatim quote reaches the API. Clinician review of the five screens still to be recorded. |
| Contradictions (real minus false alarms) | ≥ 5 | **5 counted, 0 known false alarms**, plus 3 documentation notes shown separately | `python3 -m compare.build` (prints all findings). See §2. |
| Load time (slowest of five) | < 10 s | **144 ms** API (long mode), **115 ms** (short mode), measured on the integration build with the routing knowledge base; **453 ms** in the app, submit to rendered facts | `python3 -m eval.run_api` (median and slowest over repeated requests); Playwright timing in the app. |

Additional checks:

| Check | Result |
|---|---|
| Unit tests (`make test`, `python3 -m unittest security.test_security`) | all pass |
| 15 unseen situations (`eval/unseen_situations.json`) in the app, including a German and a misspelled request | 15 / 15 render, 0 console errors, each ≤ 0.5 s |
| Production build (`cd mobile && npm run build`) | passes |

## 2. Contradictions

Counted (passages that cannot all be true; every passage linked on screen):

| # | Check | Kind |
|---|---|---|
| 1 | BMI recomputation | stated BMI does not match height and weight in the same letter (2015 letter) |
| 2 | BMI recomputation | same check, outpatient letter April 2016 |
| 3 | Event date | one biopsy, two different dates in two documents |
| 4 | Event date | one admission, two different dates in the same letter |
| 5 | Laterality | the side of one finding differs between passages, including within one letter |

Documentation notes (shown, not counted): a case number that differs within one stay, a lymph-node finding whose side cannot be compared across methods, and an invalid date written in a letter.

Suppressed as false alarms by design: small height differences, values that changed over time (weight, a dose change between medication lists), different blood-pressure readings at different times, and anything that differs only from IBM's JSON files.

## 3. Reproducing the numbers

```bash
make build                                  # pipeline + compare -> data/build/
make test
python3 -m eval.run --strict                # 15/15 + invariant violations, report in data/build/eval_report.md
make backend                                # API on :8000 (separate terminal)
python3 -m eval.run_api                     # HTTP scorer with latency
cd mobile && npm ci && npm run dev          # app on :5173
```

The in-app check (Playwright) types each situation, waits for the facts section and searches the rendered text for the answer tokens of `eval/answer_keys.json`. It is being added to `mobile/e2e/` so it runs from the repository.

## 4. Video (≤ 2 minutes)

| Time | On screen | Say |
|---|---|---|
| 0:00–0:15 | The open items and the BMI conflict | The problem: letters copy old values forward, and facts silently disappear. |
| 0:15–0:45 | Anaesthetist situation typed; facts appear; tap a source | One sentence in, one screen out. Every fact opens the sentence it comes from. |
| 0:45–1:05 | "Not in the latest letter" items | What you would miss by reading only the newest letter. |
| 1:05–1:25 | Surgeon, emergency, then a role typed live | Same patient, different task, different screen, including roles we did not prepare. |
| 1:25–1:45 | Contradictions vs documentation notes | Five real contradictions, each with all its passages; notes are kept apart. |
| 1:45–2:00 | Metrics table | 15/15, 0 invented facts, under half a second. One honest limitation (see README). |

Rules: record from the `demo-v1` tag; no claim that is not in the table above; say what does not work yet.

## 5. Pre-submission checklist

- [ ] `git log --all -- data` and `git log --all -- '*.zip'` show nothing; no document text in screenshots, fixtures or test artefacts.
- [ ] Fresh clone on another machine: README steps run end to end with the organisers' zip.
- [ ] Omar's branch merged; `make test`, `eval.run --strict`, `eval.run_api` and the in-app check re-run on `main`; numbers above updated.
- [ ] `git tag demo-v1` on the tested commit and pushed.
- [ ] Deployed URL works behind the password gate and serves the mobile app.
- [ ] README limitations match the tagged build.
- [ ] Video ≤ 2:00, recorded from `demo-v1`.
- [ ] Repository made public only after the checks above.
