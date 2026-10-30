# Second Look: mobile frontend

Responsive, phone-first web app for Track 1: a clinician picks a role, types a task, and gets one screen of the
patient facts that task needs, each linked to its source. Opens in a phone browser, no native build.

Stack: React 19, Vite, TypeScript, Tailwind CSS 4, shadcn/ui primitives, Watermelon UI components
(quick-switcher, expandable-profile-card, continuous-tabs, alert, bionis-dashboard layout), Hugeicons,
Motion, Recharts (dashboard only, lazy-loaded).

Layouts: phone (< 768 px, one column), tablet (2-column fact grid), desktop (≥ 1024 px, sticky left column
with patient card and view controls).

## Run

```bash
cd mobile
npm install
npm run dev          # http://localhost:5173, also on the LAN for phone testing
npm run build        # type-check + production build
```

## Status

Runs end to end on **mock data** (`src/data/mockFacts.ts`, `src/data/mockStats.ts`: invented patients and
numbers, no IBM data).

| Screen / part | Status |
|---|---|
| Start: role chips, task bar with display / read-aloud mode | done |
| Loading: skeleton, 10 s timeout, error + retry | done |
| Results: patient card with trust counts + stats panel, contradictions, fact cards, source and guideline sheets | done |
| Übersicht / Verlauf tabs: screen-wide switch, value history (trend line + dated values) on facts that have one | done |
| Dashboard tab (3rd level): proof ring, change tiles, weight and recorded-vs-calculated BMI charts, blood-pressure comparisons, dated facts without trends. All derived numbers computed in `src/lib/stats.ts`; no scores, predictions or advice | done |
| Read-only notice ("Second Look ändert keine Daten") on results and flag sheet | done |
| Responsive layouts (phone, tablet, desktop) | done |
| Read aloud (Web Speech API, German voices only, prefers on-device voices) | done |
| Source viewer with the three tracks (dialog-stack), flag form, PDF export, EN/DE toggle | to do |

## Not yet connected to the backend

`src/lib/api.ts` → `fetchPatientBrief(role, task)` and `fetchPatientStats(patientId)` are the only places
data is fetched; both return mock data. The app's data shape (`src/types/fact.ts`: `PatientBrief`, `Fact`, `Contradiction`) does **not**
match the backend's `Briefing` (`frontend/lib/api.ts`, `backend/app/schema.py`): the backend groups
facts under `needs`, uses trust values `consistent | conflicting | stale | single`, returns `findings`
instead of contradictions, cites `segment_ids` instead of excerpt text, and takes one `situation`
string instead of role + task. Connecting needs either a mapping layer in `api.ts` or an agreed shared
schema.

## Layout

```
src/screens/      RoleTaskSelectScreen, LoadingScreen, ResultsScreen, StyleguideScreen (/dev/styleguide, dev only)
src/components/   TaskBar, PatientCard, FactCard, ContradictionCard, ViewTabs, ValueHistory, Sparkline
src/components/dashboard/   PatientDashboard (lazy), ProofRing, MetricTile, WeightChart, BmiChart, FactPanels, Panel
src/components/ui/          app-level Button, Card, Badge, Modal, Chip, Icon, Skeleton, Notice (use these)
src/components/primitives/  shadcn/ui source the ui/ components wrap
src/theme/theme.css         all color tokens, with measured contrast ratios
src/i18n/strings.ts         every UI string (German), ready for the EN/DE toggle
src/lib/          api (fetch), stats (dashboard arithmetic), speech (read aloud), utils
src/types/        fact.ts (data contract), stats.ts (dashboard inputs), request.ts (screen-to-screen state)
```

UI copy is factual only ("Verifiziert", "Nicht dokumentiert", "Widerspruch"), never advisory.
