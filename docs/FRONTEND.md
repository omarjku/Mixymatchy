# Frontend plan — Second Look

> **For the developer and their Claude Code session.** Start Claude in the repo root and say:
> *"Read docs/FRONTEND.md, docs/CHALLENGE.md and frontend/lib/api.ts. Then do Phase 1. Follow the Rules section exactly."*
> Work phase by phase. Each phase ends with its acceptance checks green.

---

## 1. What we are building (30-second version)

A clinician types who they are and what they are doing. One screen shows:

1. **the facts that task needs**, each linked to the exact sentence in the original German letter,
2. **"not documented" / "not applicable"** where the letters are silent,
3. **what the record gets wrong**: contradictions, facts the latest letter forgot, open follow-ups.

Pitch: *"Other tools summarise the record. Second Look checks it — for the task in front of you."*

The backend already works (15/15 expected answers, ~20 ms per briefing). **The frontend is now the product the jury sees.**

### How the jury scores (docs/CHALLENGE.md)
| What | Frontend impact |
|---|---|
| Correct answers: expected answer **visible without clicking** (scrolling OK) **with a link** to a source doc | Never hide a fact behind a click/accordion if it can answer a question. `should` needs may collapse, but only behind a clearly labelled toggle, and never facts from `must` needs. |
| Traceability: link shows the **right passage** | Every source link opens the passage **highlighted and scrolled into view**. |
| Invented facts = 0 | The UI never writes clinical text of its own. It renders only strings from the API. |
| Contradictions: real ones **minus false alarms**, each linking **all** its passages | Show `tier: "contradiction"` separately from `tier: "documentation_note"`; every passage of a conflict must be openable. |
| Load time < 10 s | Show the screen as soon as the response arrives; skeletons while loading. |
| Jury: "Would a clinician trust and use this?", "Does the screen change with role/task?", "Works on new situations?" | Calm, dense, scannable clinical UI; visible lens switch; graceful generic screen for unknown roles. |

---

## 2. Rules (non-negotiable)

1. **No patient data in git.** Never commit screenshots, fixtures or test snapshots containing document text. Playwright artefacts go to a git-ignored folder. Use synthetic text in unit tests and Storybook-style examples.
2. **Render, don't write.** Every clinical string comes from the API (`label_en`, `value`, `explanation`, passage text). The UI may add only fixed UI labels ("Not documented", "Source", "Possible copy error").
3. **Every fact has a source link.** A fact row without `segment_ids` is a bug: show it in red in dev mode and fail the e2e test.
4. **Every number is computed.** Counts ("9 of 30", "66 facts") come from `briefing.stats`, never hard-coded.
5. **Never colour alone** (WCAG 1.4.1). Every status = icon **+** text label (e.g. ✓ "Consistent", ⚠ "Conflicting", ⌛ "Outdated", ○ "Not documented", – "Not applicable").
6. **Wording:** "possible copy error" (never "copied wrong"); "documentation note" (never call it a contradiction); "Not documented" (never "unknown/none").
7. **Footer on every screen:** "Decision support only — clinician review required. All facts are quoted from the patient's documents."
8. **No advice.** No "stop", "give", "recommend" text anywhere in the UI.
9. Dates shown as `DD.MM.YYYY` (the documents are Austrian) with the ISO date in a tooltip.

---

## 3. Current state

```
frontend/
  app/layout.tsx, app/page.tsx      single page: input, role chips, briefing, findings, proof bar
  components/SourcePane.tsx          multi-document passage viewer with <mark> highlights
  lib/api.ts                         TypeScript types mirroring backend/app/schema.py + fetch helpers
  next.config.ts                     STATIC_EXPORT=1 -> static site served by FastAPI in deployment
```
Stack: Next.js 15.5, React 19.1, Tailwind 4.1, TypeScript 5.9. No component library yet.

### Run it
```bash
# backend (repo root; builds data/build/ on first start — needs data/ locally)
python -m uvicorn --app-dir backend app.main:app --port 8000
# frontend
cd frontend && npm install && npm run dev        # http://localhost:3000
```
`NEXT_PUBLIC_API_URL` defaults to `http://127.0.0.1:8000` (use 127.0.0.1, not localhost: avoids a 2 s lookup delay on Windows).

### API (see `backend/app/schema.py`; keep `frontend/lib/api.ts` in sync)
| Endpoint | Returns |
|---|---|
| `POST /briefing {situation}` | `Briefing` |
| `GET /documents` | list of documents (no text) |
| `GET /documents/{id}` | document + `text` + `segments[]` with `start/end` offsets into `text` |
| `GET /segments/{id}` | one segment |
| `GET /health` | backend, document and fact counts |

`Briefing` shape (real payload, anaesthetist situation):
```
situation, role, task, as_of
needs[]        need, label, status: documented | not_documented | not_applicable
               facts[]      id, type, concept, label_en, value, unit, date, side, status,
                            segment_ids[], trust: consistent | conflicting | stale | single
               computed[]   label, value, formula, segment_ids[]      (e.g. weight change)
               superseded[] older facts replaced by newer documents / newer medication list
               reason, reason_segment_ids                              (not_applicable evidence)
blind_spot[]   facts missing from the latest letter
findings[]     kind: conflict | dropped | followup | silence
               tier: contradiction | documentation_note | null
               title, explanation, segment_ids[], severity
stats          facts_shown, facts_verified, facts_dropped, computed_values, not_documented,
               not_applicable, blind_spot, task_concepts, contradictions, documentation_notes,
               followups_open, engine_ms
```
Typical size: ~27 needs, ~66 facts, ~9 blind-spot facts, 8 conflicts.

### Backend dependencies (ask Omar; build the UI against mocks meanwhile)
| Need from backend | Used by | Status |
|---|---|---|
| `priority: must | should` on each need | collapse `should` needs | missing (adapter drops it) |
| safety-strip flag on needs (allergies, blood thinners, current meds, problems) | sticky safety strip | merged into `needs`, no flag |
| fact families / propagation chains (`compare.json → propagation`) | Family tree | computed by engine, not in API |
| English translation per segment | Source pane | missing |
| LLM situation parser (`SECOND_LOOK_LLM=1`) | unseen roles | exists, off by default |

Until these land, type them as optional fields in `api.ts` and hide the feature when absent.

---

## 4. Screen design

### Layout (desktop ≥ 1280 px; tablet stacks the source pane as a bottom sheet)
```
┌───────────────────────────────────────────────────────────────────────────────┐
│ Second Look · Patient banner (name, sex, DOB, "8 documents · as of 15.04.2016")│
│ [ Who are you and what are you doing?                       ] [Build briefing] │
│ Lens: (Anaesthetist) (Surgeon) (GP) (Emergency) (+ any role)    examples ▾     │
├───────────────────────────────────────────────┬───────────────────────────────┤
│ SAFETY STRIP  allergies · blood thinners · current meds · problems (sticky)    │
├───────────────────────────────────────────────┤  SOURCE PANE (resizable)      │
│ ⚠ BLIND SPOT  You would miss 9 of 30 facts…   │  Letter title · date · dept   │
│   (max 1 callout; list, each with source)     │  …text… [highlighted passage] │
│                                               │  EN: machine translation      │
│ WHAT YOU NEED                     [must ▸ should]│  Other mentions: 3 ▸        │
│ ┌ Blood thinners ───────────────────────────┐ │                               │
│ │ ✓ Consistent  <label_en> <value>  12.06.15│ │  — or, for a conflict —       │
│ │               [Source 1] [Source 2]       │ │  passage A  |  passage B      │
│ └───────────────────────────────────────────┘ │  side by side                 │
│ ┌ Airway ── ○ Not documented ───────────────┐ │                               │
│ ┌ Weight ── = Change −X kg (formula) [srcs] ┐ │                               │
│                                               │                               │
│ THE RECORD DISAGREES (5)   DOCUMENTATION NOTES (3)                             │
│ OPEN FOLLOW-UPS (2)                           │                               │
├───────────────────────────────────────────────┴───────────────────────────────┤
│ 66 facts · 66 verified word-for-word · 0 dropped · built in 41 ms  │ footer    │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Components (each = one file in `frontend/components/`)
| Component | Purpose | Acceptance criteria |
|---|---|---|
| `SituationInput` | free text + Enter submit + example situations dropdown | submits on Enter; disabled while loading; keeps last text |
| `LensSwitcher` | role chips that re-run the briefing with the same task | active chip visible; screen re-arranges with a layout animation |
| `PatientBanner` | who + as-of date | always visible (prevents wrong-patient errors) |
| `SafetyStrip` | allergies, blood thinners, current meds, active problems | sticky under header; same on every lens |
| `BlindSpotCallout` | `blind_spot` + `stats.blind_spot / stats.task_concepts` | NHS warning-callout pattern: one per screen, short heading, each item has a source link |
| `NeedCard` | one need: label + status + facts/computed/superseded | `must` needs expanded; `not_documented` shows ○ text; `not_applicable` shows reason + evidence link |
| `FactRow` | label, value, date, trust badge, source chips | ≥ 1 source chip; chips grouped per document (doc short name + date) |
| `TrustBadge` | ✓ Consistent / ⚠ Conflicting / ⌛ Outdated / • Single source | icon + text + tooltip explaining the mark |
| `ComputedRow` | computed value with `=` icon, formula in tooltip | links every input segment |
| `SupersededDisclosure` | "2 older values replaced by newer documents" | collapsed by default; opens list with sources |
| `FindingsPanel` | tabs or sections: Contradictions · Documentation notes · Open follow-ups · Dropped | counts from `stats`; contradiction cards open **all** passages side by side |
| `ConflictCompare` | 2+ passages next to each other, differing values emphasised | each passage labelled with document + date |
| `FamilyTree` | how one fact travelled across letters (date-ordered vertical timeline) | nodes: original / consistent / "possible copy error" / dropped; each node opens its passage. Start with a CSS timeline; React Flow only if needed |
| `SourcePane` | highlighted passage, scroll into view, multiple documents, "other mentions" | highlight exactly `text[start:end]`; keyboard focusable; translation slot |
| `ProofBar` | verified counts + engine time | numbers only from `stats` |
| `ReviewFooter` | safety statement (Rule 7) | on every screen |

### Visual language
- **Tone:** calm clinical tool, not a dashboard. White surface, one accent (teal `#0F6E6E`), semantic colours only for status: green `#2E7D4F` consistent, red `#B4372F` conflict/blind spot, amber `#A86A00` outdated, slate `#5B6573` not documented.
- **Density:** 14 px body, 13 px secondary, line-height 1.5; card padding 12–16 px. Clinicians scan, so align values in a column.
- **Typography:** Inter (or system UI) for UI; tabular numbers (`font-variant-numeric: tabular-nums`) for values and dates.
- **Icons:** lucide-react only. Every icon next to text; decorative icons `aria-hidden`.
- **Motion:** only for the lens switch (layout animation, ≤ 250 ms) and opening the source pane. Respect `prefers-reduced-motion`.
- **Callouts:** at most 2 coloured callouts per screen (NHS guidance) — blind spot + contradictions; everything else is plain cards.

---

## 5. Libraries to add

| Library | Why | Install |
|---|---|---|
| **shadcn/ui** (Radix-based, Tailwind v4 + React 19 ready) | accessible primitives: Tabs, Tooltip, Collapsible, Badge, Card, Sheet, ScrollArea, Skeleton, Resizable | `npx shadcn@latest init`, then `npx shadcn@latest add tabs tooltip collapsible badge card sheet scroll-area skeleton resizable separator` |
| **lucide-react** | icons (installed by shadcn) | — |
| **motion** | lens-switch layout animation (`motion/react`, `layout`, `LayoutGroup`, `AnimatePresence`) | `npm i motion` |
| **react-resizable-panels** | source-pane split (via shadcn `resizable`) | added by shadcn |
| **@xyflow/react** *(optional)* | only if the family tree needs a graph instead of a vertical timeline | `npm i @xyflow/react` |
| **@playwright/test + @axe-core/playwright** | e2e + accessibility checks | `npm i -D @playwright/test @axe-core/playwright && npx playwright install chromium` |

Pin exact versions in `package.json` (we pin everything). Run `npm audit` after installing.

---

## 6. Work plan

Each phase is one PR to `main` (branch `ux/<phase>`). Before merging: `npm run typecheck && npm run build`, Playwright green, `python -m pytest -q` in `backend/` still green.

### Phase 1 — Foundation (½ day)
- shadcn init, design tokens in `globals.css` (`@theme` colours above), Inter, lucide.
- Split `page.tsx` into the components in §4 (logic unchanged).
- `lib/api.ts`: add optional fields from the dependency table; add a `mock` mode (`NEXT_PUBLIC_MOCK=1`) that loads a **synthetic** briefing from `frontend/mocks/briefing.synthetic.json` (invented drug names/values, no patient text).
- ✅ Done when: same features as today, new components, mock mode works, build passes.

### Phase 2 — Trust & traceability (1 day) ← most points
- `FactRow` + `TrustBadge` + source chips per document; `NeedCard` statuses incl. `not_applicable` with evidence.
- `SourcePane`: resizable split, exact highlight, scroll-into-view, focus management, "other mentions" list.
- `ComputedRow`, `SupersededDisclosure`, `ProofBar`, `ReviewFooter`, `PatientBanner`.
- ✅ Done when: for all 5 situations every expected answer is visible without clicking and its source chip highlights the right passage (Playwright test, §7).

### Phase 3 — The "audit" layer (1 day) ← memorability
- `BlindSpotCallout` (computed "X of Y").
- `FindingsPanel` with Contradictions vs Documentation notes vs Open follow-ups vs Dropped, counts from `stats`.
- `ConflictCompare` side-by-side passages.
- `FamilyTree` (vertical timeline; uses backend propagation once available, otherwise hidden).
- ✅ Done when: all 5 counted contradictions open all their passages side by side; notes are visually distinct and never labelled "contradiction".

### Phase 4 — Lens switch & any-role input (½ day)
- `LensSwitcher` re-runs the briefing with the role swapped, keeping the task; `motion` layout animation between screens.
- Example-situation dropdown (the 5 cases + 5 unseen ones from `eval/unseen_situations.json`).
- Generic-role screen looks intentional (heading "General overview for <role>").
- ✅ Done when: switching Anaesthetist → Surgeon → Emergency visibly re-arranges in < 1 s; the 15 unseen situations render without errors.

### Phase 5 — Polish, accessibility, demo (½–1 day)
- Skeleton loading, empty/error states, keyboard navigation, `prefers-reduced-motion`.
- axe: 0 serious/critical violations. Greyscale check (everything understandable without colour).
- Optional: integrate the lock screen from `security/web/second-look-lock.js` (`SecondLook.lock.init({ appRoot: '#app', ... })`).
- Static export check: `STATIC_EXPORT=1 npm run build` works (deployment serves `frontend/out`).
- ✅ Done when: demo script (§8) runs end to end without a hiccup.

### Parallel Claude agents (one git worktree each)
| Agent | Task card |
|---|---|
| A · components | "Build Phase N components in `frontend/components/` per docs/FRONTEND.md §4; use shadcn primitives; no clinical text in code." |
| B · tests | "Write Playwright tests in `frontend/e2e/` per §7; artefacts to `frontend/test-results/` (git-ignored)." |
| C · reviewer (read-only) | "Audit the UI against docs/FRONTEND.md Rules 1–9 and WCAG 1.4.1; list violations with file:line." |

---

## 7. Tests

`frontend/e2e/` (Playwright, Chromium, backend running):
1. **Five situations:** for each case in `cases/situations.md`, submit title + description; for each expected answer, assert the key tokens from `eval/answer_keys.json` are visible **without clicking**, and that at least one adjacent source chip belongs to an expected source document.
2. **Traceability:** click every source chip on the 5 screens; assert the pane shows a `<mark>` whose text equals the segment text from `/segments/{id}`.
3. **No unlinked facts:** every `[data-fact]` has ≥ 1 `[data-source]`.
4. **Numbers are computed:** proof-bar numbers equal `stats` from the API response.
5. **Unseen situations:** all 15 in `eval/unseen_situations.json` render, no console errors.
6. **Accessibility:** `new AxeBuilder({ page }).withTags(['wcag2a','wcag2aa']).analyze()` → no serious/critical violations.
7. **Speed:** submit → last card rendered < 2 s locally.

Add `"e2e": "playwright test"` to `package.json`. Add `frontend/test-results/` and `frontend/playwright-report/` to `.gitignore`.

---

## 8. Demo script the UI must support (2-minute video)
1. Hook: blind-spot callout + weight/BMI conflict visible on first screen.
2. Anaesthetist case → click a fact → German passage highlighted, English below.
3. Blind spot: "you would miss X of Y".
4. Lens switch: Surgeon → Emergency → a role typed live.
5. Family tree of the carotid-side conflict ("possible copy error"); contradictions vs documentation notes.
6. Proof bar + metrics; one honest limitation.

---

## 9. References (checked October 2026)

**Components & libraries**
- shadcn/ui — Tailwind v4: https://ui.shadcn.com/docs/tailwind-v4 · React 19: https://ui.shadcn.com/docs/react-19
- shadcn Resizable (react-resizable-panels): https://ui.shadcn.com/docs/components/resizable
- Motion for React — layout animations: https://motion.dev/docs/react-layout-animations · AnimatePresence: https://motion.dev/docs/animate-presence
- React Flow (`@xyflow/react`), only for a graph-style family tree: https://www.npmjs.com/package/@xyflow/react
- Playwright + axe: https://www.npmjs.com/package/@axe-core/playwright

**Clinical UI patterns (borrow the pattern, not the library)**
- NHS design system — Warning callout (when to use, max 2 per page): https://service-manual.nhs.uk/design-system/components/warning-callout
- Summary list pattern (key–value rows; GOV.UK origin, also in NHS): https://govuk-components.netlify.app/components/summary-list
- Medplum React components (clinical patterns such as patient timeline; Mantine-based, do **not** install): https://www.medplum.com/docs/api/react · Storybook: https://storybook.medplum.com
- IBM Carbon — status indicator pattern (IBM sponsors the track): https://carbondesignsystem.com/patterns/status-indicator-pattern/

**Evidence for design decisions**
- WCAG 1.4.1 Use of Color (icon + text for status): https://alphagov.github.io/wcag-primer/sc/1.4.1.html
- Alert fatigue — tailor CDS to roles, tiered display (JAMIA 2019): https://pmc.ncbi.nlm.nih.gov/articles/PMC6748819
- Usability principles for medication alerting (BMC Med Inform 2018): https://link.springer.com/10.1186/s12911-018-0615-9
- "Elements of Style for Interruptive EHR Alerts" (2025): https://www.thieme-connect.de/products/ejournals/pdf/10.1055/a-2508-7039.pdf

Treat third-party pages as guidance; check the official docs for exact APIs before coding.
