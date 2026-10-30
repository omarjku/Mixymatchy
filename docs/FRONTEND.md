# Frontend plan: Second Look (mobile app)

> **For Zoha and her Claude Code session.** Open Claude in the repo root and say:
> *"Read docs/FRONTEND.md, docs/INTEGRATION.md, docs/CHALLENGE.md, docs/design/prototype.html and docs/contract/briefing.example.json. Then do Phase 1. Follow the Rules exactly."*
> Work phase by phase; each phase ends with its checks green.

**Decision (30.10.2026):** the demo frontend is Zoha's phone-first app in `mobile/` (Vite, React 19, Tailwind 4).
`frontend/` (Next.js) stays only as a reference implementation of the API wiring and source highlighting; do not extend it.

---

## 1. What we are building

A clinician types who they are and what they are doing. One screen shows:
1. **the facts that task needs**, each with the sentence from the original German letter it comes from,
2. **"Not documented" / "Not applicable"** where the letters are silent,
3. **where the record is wrong**: contradictions, facts the latest letter dropped, open follow-ups.

Pitch: *"Other tools summarise the record. Second Look checks it, for the task in front of you."*

The backend already answers all 15 test questions correctly in ~20 ms. **The frontend is what the jury sees and remembers.**

### How the jury scores it (docs/CHALLENGE.md)
| Scoring rule | What it means for the UI |
|---|---|
| Expected answer visible **without clicking** (scrolling OK), **with a link** to a source document | Facts from P1 needs are never inside a closed accordion, tab or sheet, in short or full mode. |
| Traceability: the link shows the **right passage** | Every fact shows its quote inline; tapping opens the letter with that passage highlighted. |
| Invented facts = 0 | The UI renders only API strings. Nothing from `mockFacts.ts` may reach the demo. |
| Contradictions minus false alarms, each linking **all** passages | Counted contradictions and documentation notes look different; every passage of a conflict is shown. |
| Load time < 10 s | Skeleton immediately; the full screen when the response arrives. |
| "Would a clinician trust it?", "Does the screen change with role/task?", "Works on new situations?" | Calm, evidence-first screen; visible lens switch; any role accepted as free text. |

**The jury writes situations in English.** English is the default UI language; German stays as a toggle.

---

## 2. Rules (non-negotiable)

1. **No patient data in git.** No screenshots, fixtures or snapshots with document text. Mock data stays invented (as `mockFacts.ts` is today) and is never shown in the demo.
2. **Render, don't write.** Every clinical string comes from the API. The UI adds only fixed labels ("Not documented", "Possible copy error", ...).
3. **Every fact has a source.** A fact without `segment_ids` is a bug: show it red in dev mode and fail the e2e test.
4. **Every number is computed** from `briefing.stats` or counted from the payload. Never typed in.
5. **Never colour alone** (WCAG 1.4.1): every status is text, optionally with an icon.
6. **Wording:** "Possible copy error" (never "copied wrong"); "Documentation note" (never called a contradiction); "Not documented" (never "unknown").
7. **Footer on every result screen:** "Decision support only. A clinician reviews every fact before acting."
8. **No advice, and knowledge stays apart from facts.** The current guideline excerpts that read as instructions (e.g. "pause anticoagulants...") go. Two kinds of non-patient text are allowed, each only in its own sheet and never styled like a patient fact:
   - **"Why this is shown"**: `need.why[]` (guideline title, body, link from Mani's knowledge base). Explains why the need is on the list; never a recommendation for this patient.
   - **"From the drug label"**: `label_panels[]`, **long mode only**, each listed item beside the related patient fact status (found with source, ruled out, not documented). Never "contraindicated", never "fit".
   Neither appears on the default (short) screen of the five demo situations, so the jury cannot count them as invented facts.
9. Dates as `DD.MM.YYYY`; months as "Jun 2015".

---

## 3. Design direction: "the annotated letter"

The record is a stack of paper discharge letters. Second Look is the senior colleague's review of it: **highlighter** on what matters, **red pen** where the record contradicts itself, **margin notes** for what is missing. Everything else stays quiet.

See `docs/design/prototype.html` (open in a browser at 390 px) and `docs/design/prototype.png`. Both use invented data.

### Critique of the current `mobile/` build (honest, so we fix the right things)
Good, keep: inline contradiction quotes, distinct "not documented" row, flag button, read-aloud, bottom sheets, disclaimer, IBM Plex Sans.
Reads as generic AI build, change:
- Tailwind-indigo accent and indigo pill buttons everywhere.
- Every block the same rounded white card with the same soft shadow.
- "Big number + small label" stat-tile trio in the patient card.
- Meta strings joined with middle dots ("Anästhesie · Prämedikation ...").
- A "Verifiziert" badge on every fact: noise, and everything on screen is verified anyway.
- Start screen is mostly empty space with four role chips (the jury will use other roles).
- Evidence hidden behind a "Quelle" button: the strongest thing we have is invisible.

### Tokens
| Token | Hex | Use (only this) |
|---|---|---|
| `paper` | `#F5F6F3` | app background (cool clinical paper, not cream) |
| `sheet` | `#FFFFFF` | grouped lists and sheets |
| `ink` | `#1D3C8F` | links, active lens, focus ring (Königsblau, the classic fountain-pen ink) |
| `text` | `#1F242B` | body text |
| `muted` | `#5E6570` | secondary text, "Not documented" |
| `highlighter` | `#FFE15A` | the cited words inside a quote, nothing else |
| `red-pen` | `#BF2A2F` (+ soft `#FBEDEC`) | contradictions and the blind-spot margin note, nothing else |
| `sage` | `#2E7550` | "Consistent in N letters" |
| `amber` | `#8A6A12` | "Outdated" |
| `rule` | `#E2E4DF` | row separators |

**Type: one rule carries the whole concept. Serif means quoted from the record; sans means the app speaking.**
- IBM Plex Sans 400/500/600: all UI (already in the app; IBM sponsors the track).
- IBM Plex Serif 400: every verbatim quote from the letters, in German quotation marks „…“.
- Scale: 13 / 15 / 16 / 19 px; body line-height 1.5; serif quotes 1.45; tabular numbers for values and dates.
- No all-caps labels, no eyebrow labels, no monospace, no "→" on buttons.

### Layout (390 px, one column, left aligned)
```
Erika Beispiel, female, born 02.07.1961. 6 letters, Mar 2024 to Jan 2025     <- patient line, sticky
Anaesthetist, pre-op check before hip replacement on 12 Feb 2025             <- the user's own sentence as title
Anaesthetist  Surgeon  GP  Emergency  Other role                             <- lens tabs, ink underline
┃ Not in the latest letter                                                   <- red-pen margin note (1 per screen)
┃ 3 of 14 facts for this task appear only in older letters.
┃ Sleep apnoea  last written 14.03.2024 ...
What you need                                                                <- sentence-case section heading
┌ Blood thinner                                   Consistent in 3 letters ┐  <- one grouped list, hairline rows
│ Clopidogrel 75 mg, mornings                                             │
│ „Plavix 75mg 1 0 0 0“   (serif, cited words highlighted)                │
│ Discharge letter, 20.01.2025   (ink link -> source sheet)               │
│ Airway assessment                                   Not documented      │
└──────────────────────────────────────────────────────────────────────────┘
The record disagrees                                                          <- red-pen cards, value circled
Documentation notes / Open follow-ups                                         <- quiet lists
23 facts, each quoted word for word from the letters. 2 conflicts, 1 note.  <- proof sentence, not tiles
Decision support only. A clinician reviews every fact before acting.
```

### The one memorable moment
Tapping a source link opens the letter sheet: letterhead line (document title, department, date), the surrounding lines in serif, and the cited passage receives a **highlighter sweep** (background grows left to right, ~350 ms, `prefers-reduced-motion` = instant). This is the only animation besides the lens switch. No fade-in-on-scroll, no hover effects on cards.

### Self-check before every PR
Remove one accessory. If a new element is a card, a badge or a coloured block, ask whether a plain row would do.

---

## 4. Connecting to the backend

**The contract is `docs/INTEGRATION.md` §3 (API v2).** Build against `docs/contract/briefing.example.json` and `docs/contract/document.example.json` (invented data) in mock mode (`VITE_MOCK=1`); switching to the real backend is then only `VITE_API_URL`. v2 fields are optional: hide a feature when its field is missing, so the app works against today's backend too.

Today `mobile/src/lib/api.ts → fetchPatientBrief(role, task)` returns mock data. Replace it with a mapping layer; keep `PatientBrief` only if it still fits, otherwise adopt the backend types directly.

### New in v2 (from Mani's routing knowledge base, `docs/knowledge-base/`)
| Field | UI |
|---|---|
| `detail: short / long` (request) | toggle "Short / Full" in the header. Short = P1 needs; Full adds P2, P3 and label panels. Default short. |
| `need.priority` P1 / P2 / P3 | P1 always expanded; P2 under "More context"; P3 under "On request" (Full only) |
| `route.role_label`, `route.bundle_titles` | subtitle under the user's sentence, e.g. "Pre-procedure check (anaesthesia)" |
| `route.layer` ≠ `kb`, `route.note` | quiet note above the list: "No exact match for this request. Showing a composed selection." / "Answered by searching the letters." Never hide which layer answered. |
| `need.status: ruled_out` | "Ruled out" with its quote (a documented negative), visually different from "Not documented" |
| `need.searched` | "Not documented. Searched 6 letters for Mallampati, Atemweg, …" and, if set, a link to the empty lab table |
| `need.added_by_rule` | small note "Added because a blood thinner is listed" (text from the rule title) |
| `need.why[]` | "Why this is shown" link opening the guideline sheet (Rule 8) |
| `computed[].from / to / delta / delta_pct / note` | change row: "72 kg to 64 kg, −8 kg (−11.1%)", both inputs linked, note in muted text |
| `finding.check_id` | check name in the conflict details (X01 "BMI recomputation", X03 "Laterality conflict", …) |
| `label_panels[]` | "From the drug label" sheet beside a medication (Full only) |
| `POST /segments {ids}` | one request for all inline quotes |

### Computed values: what to show (Mani's statistics review, `docs/INTEGRATION.md` §4)
- Changes, always with both inputs linked: weight (absolute + percent of the earlier value), BMI **recorded vs calculated** per letter (keep the written value, flag the difference), prescribed daily dose of the same drug, blood-pressure comparisons only when the task needs them.
- Dated facts, never trend lines: single HbA1c, LVEF, sparse heart rate/temperature, height, tumour markers. No sparkline for fewer than 3 comparable values.
- Never: p-values, baseline bands, predictions, anomaly scores, per-day rates, or any cause/intent wording.

| Backend | Endpoint / field | Notes |
|---|---|---|
| `POST /briefing {situation}` | one free-text sentence | Send the user's sentence. If a lens is tapped, send `"<Role>, <task text>"`. |
| `needs[]` | `need, label, status, facts[], computed[], superseded[], reason, reason_segment_ids` | `status`: `documented`, `not_documented`, `not_applicable` |
| `facts[]` | `label_en, value, unit, date, segment_ids[], trust` | `trust`: `consistent`, `conflicting`, `stale`, `single` |
| `blind_spot[]` | facts missing from the latest letter | count: `stats.blind_spot` of `stats.task_concepts` |
| `findings[]` | `kind` (`conflict`, `dropped`, `followup`, `silence`), `tier` (`contradiction`, `documentation_note`), `title, explanation, segment_ids` | |
| `GET /segments/{id}` | `text, doc_id, start, end` | the inline quote under each fact |
| `GET /documents/{id}` | `title, date, department, text, segments[]` | source sheet with surrounding lines; highlight `text[start:end]` |
| `stats` | counts + `engine_ms` | proof sentence |

Fetch all segments for one briefing in parallel (≈ 60 small requests) or ask Omar for a batch endpoint `POST /segments {ids}`; cache documents per session.

Base URL from `VITE_API_URL` (default `http://127.0.0.1:8000`; not `localhost`, which adds ~2 s on Windows). Run the backend from the repo root: `python -m uvicorn --app-dir backend app.main:app --port 8000` (needs `data/` locally).

### Still to request from Omar (not yet in the v2 contract)
| Field | For |
|---|---|
| safety-strip flag (allergies, blood thinners, current meds, problems) | sticky strip under the patient line |
| propagation / fact families from `compare.json` | "how this fact travelled" timeline |
| English translation per segment | translation under the German quote |

---

## 5. Work plan

Branch per phase from `mobile-frontend`; small PRs. Before merging: `npm run build` and the e2e tests green; `python -m pytest -q` in `backend/` unaffected.

### Phase 1: Contract and real data (½ day)
- Types for API v2 (`docs/INTEGRATION.md` §3); mock mode on `docs/contract/*.example.json`; mapping layer in `src/lib/api.ts`.
- One free-text input (role chips become example sentences); English default, DE toggle kept.
- Short / Full toggle wired to `detail`; route subtitle and fallback note.
- Delete the guideline-advice excerpts from the result screen (Rule 8).
- ✅ The example JSON renders end to end; the 5 situations from `cases/situations.md` render real facts from the API.

### Phase 2: Evidence first (1 day), most points
- Apply tokens and type rules (§3). Facts as one grouped list with hairline rows (replace the card stack).
- Inline serif quote under every fact with the cited words highlighted; source link opens the letter sheet with the highlighter sweep.
- Trust as text ("Consistent in 3 letters", "Outdated, 10 months old", "Single letter"); "Not documented" with what was searched; "Ruled out" with its quote; "Not applicable" with its evidence link; change rows with both inputs linked (§4 rules); superseded values behind "Older values (2)".
- "Why this is shown" sheet from `need.why` (Rule 8).
- Patient line + the user's sentence as title; proof sentence; footer.
- ✅ For all 15 questions the answer and its quote are visible without clicking.

### Phase 3: The audit layer (1 day), most memorable
- Margin note "Not in the latest letter" (`blind_spot`, counted).
- "The record disagrees": red-pen cards for `tier: contradiction`, every passage shown, the differing value circled.
- "Documentation notes" and "Open follow-ups" as quiet lists, never labelled contradictions.
- "How this fact travelled": a date-ordered vertical list of letters for a conflicted fact (original, consistent, "Possible copy error", dropped). Hidden until the backend sends propagation.
- ✅ All 5 counted contradictions show all their passages; notes look clearly different.

### Phase 4: Lens and any role (½ day)
- Lens tabs re-run the briefing with the role swapped and the task kept; layout animation ≤ 250 ms (`motion/react`, `layout`).
- Lens tabs send `role_override`; "Other role" opens the free-text field. Mani's knowledge base has 20 roles (`docs/knowledge-base/routing_knowledge_base.json → roles`); use their `name` for labels.
- Example sentences: the 5 cases + 5 from `eval/unseen_situations.json`. A `route.layer` other than `kb` shows its note.
- "From the drug label" panels in Full mode (Rule 8).
- ✅ Anaesthetist to Surgeon to Emergency re-arranges in < 1 s; all 15 unseen situations and the 22 hold-out situations in the knowledge base (`validation.extra_tests`) render without errors.

### Phase 5: Polish and demo (½ day)
- Loading skeleton in the final layout shape; errors say what failed and offer "Try again".
- Keyboard and screen-reader pass; greyscale check; `prefers-reduced-motion`.
- Optional: lock screen from `security/web/second-look-lock.js`.
- Desktop ≥ 1024 px: source sheet becomes a right-hand pane (the jury may use a laptop).
- Deployment: Omar's Dockerfile serves `frontend/out`; ask him to switch it to `mobile/dist`.
- ✅ Demo script (§7) runs twice in a row without a hiccup.

### Parallel Claude agents (one git worktree each)
| Agent | Task card |
|---|---|
| Builder | "Implement Phase N in `mobile/src` per docs/FRONTEND.md; tokens and rules in §2–§3." |
| Tester | "Write Playwright tests in `mobile/e2e/` per §6; artefacts in git-ignored `mobile/test-results/`." |
| Design reviewer (read-only) | "Screenshot every screen at 390 px and 1280 px; check against §3 (tokens, serif-means-quoted, one memorable moment, no generic tells) and Rules 1–9; list issues with file:line." |

---

## 6. Tests (`mobile/e2e/`, Playwright + `@axe-core/playwright`, backend running)

1. **Five situations:** submit each case; the key tokens from `eval/answer_keys.json` are visible without clicking, next to a source from an expected document.
2. **Traceability:** every source link opens a sheet whose highlighted text equals `/segments/{id}`.text.
3. **No unlinked facts:** every `[data-fact]` has a `[data-source]`.
4. **Computed numbers:** the proof sentence matches `stats`.
5. **Unseen situations:** all 15 render, no console errors.
6. **Accessibility:** no serious or critical axe violations (`wcag2a`, `wcag2aa`).
7. **Speed:** submit to full screen < 2 s locally.

---

## 7. Demo script the UI must support (2-minute video)
1. Hook: the margin note and the weight/BMI conflict on the first screen.
2. Anaesthetist case: a fact, its inline quote, tap: the letter with the highlighter sweep.
3. "Not in the latest letter": X of Y.
4. Lens switch: Surgeon, Emergency, then a role typed live.
5. "The record disagrees": the carotid-side conflict and how it travelled ("Possible copy error").
6. Proof sentence, metrics, one honest limitation.

---

## 8. References (checked October 2026)

**Libraries**
- shadcn/ui with Tailwind v4: https://ui.shadcn.com/docs/tailwind-v4 · React 19: https://ui.shadcn.com/docs/react-19
- Motion layout animations: https://motion.dev/docs/react-layout-animations · AnimatePresence: https://motion.dev/docs/animate-presence
- Vaul drawer (already used for sheets): https://github.com/emilkowalski/vaul
- React Flow, only if the travel view needs a graph: https://www.npmjs.com/package/@xyflow/react
- Playwright + axe: https://www.npmjs.com/package/@axe-core/playwright

**Clinical UI patterns (borrow the pattern, not the library)**
- NHS warning callout (when to use; max 2 per page): https://service-manual.nhs.uk/design-system/components/warning-callout
- Summary list (key and value rows): https://govuk-components.netlify.app/components/summary-list
- Medplum React components (clinical patterns; do not install): https://www.medplum.com/docs/api/react
- IBM Carbon status indicators (shape or text with colour): https://carbondesignsystem.com/patterns/status-indicator-pattern/
- IBM Plex typefaces: https://www.ibm.com/plex/

**Evidence behind the design rules**
- WCAG 1.4.1 Use of Color: https://alphagov.github.io/wcag-primer/sc/1.4.1.html
- Alert fatigue drops with role-tailored display (JAMIA 2019): https://pmc.ncbi.nlm.nih.gov/articles/PMC6748819
- Usability principles for alerting systems (BMC Med Inform 2018): https://link.springer.com/10.1186/s12911-018-0615-9
- Elements of Style for interruptive EHR alerts (2025): https://www.thieme-connect.de/products/ejournals/pdf/10.1055/a-2508-7039.pdf
