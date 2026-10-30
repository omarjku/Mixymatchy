# End-to-end tests (mobile app + backend)

Playwright suite for docs/FRONTEND.md §6. Runs against the real backend; no mocks.

| Spec | Checks |
|---|---|
| expected answers | for each of the 5 situations (title + description from `cases/situations.md`, typed as one sentence), every answer item in `eval/answer_keys.json` is in the Key facts block (details collapsed, <= 8 lines); "Show more" opens the full cards |
| start screen | one free-text field, no role / example chips, the sentence is sent to /briefing exactly as typed |
| source links | up to 6 source buttons per situation open the full letter with the cited passage marked, in view, and verbatim in a document |
| source viewer | several passages: all marked, Next steps between them; desktop opens a side pane |
| contradictions | both passages side by side, each opens its letter |
| language toggle | English default, DE toggle and back |
| banners | not authorised (firefighter, plain message, no example chips), no task ("Anaesthetist: hi": needs_task banner, no patient card), not applicable (prostate, female patient), unknown role label (never GP), suggestions for an unrecognised task |
| speed | submit to the "read as" line visible < 2 s |
| unseen situations | the 15 situations in `eval/unseen_situations.json`, typed via "Other role / Andere Rolle", render with no console or page errors |
| accessibility | axe (WCAG 2 A/AA) on the start and results screens: no serious or critical violations |

Selectors match both the English and the German UI.

## Run

```bash
# repo root, with the organisers' data in data/ (git-ignored)
python -m pipeline.build && python -m compare.build
python -m uvicorn --app-dir backend app.main:app --port 8011      # terminal 1

cd mobile && npm ci && npx playwright install chromium   # or PW_CHROMIUM=/path/to/chrome (default /opt/pw-browsers/chromium; PW_CHROMIUM= for the pinned one)
BACKEND_URL=http://127.0.0.1:8011 npx vite --port 5181            # terminal 2 (optional: the suite starts it if absent)
npm run e2e                                                       # terminal 3
```

Environment: `E2E_BASE_URL` (default `http://127.0.0.1:5181`), `E2E_BACKEND_URL` (default `http://127.0.0.1:8011`).
Screenshots, traces and videos are off, and `test-results/` / `playwright-report/` are git-ignored: they would contain patient text.
