# Mobile frontend

Phone-first web app for Track 1: a clinician picks a role, types a task, and gets one screen of the
patient facts that task needs, each linked to its source. Opens in a phone browser, no native build.

Stack: React 19, Vite, TypeScript, Tailwind CSS 4, shadcn/ui primitives, Watermelon UI components
(quick-switcher, expandable-profile-card), Hugeicons, Motion.

## Run

```bash
cd mobile
npm install
npm run dev          # http://localhost:5173, also on the LAN for phone testing
npm run build        # type-check + production build
```

## Status

Runs end to end on **mock data** (`src/data/mockFacts.ts`, invented patients, no IBM data).

| Screen / part | Status |
|---|---|
| Start: role chips, task bar with display / read-aloud mode | done |
| Loading: skeleton, 10 s timeout, error + retry | done |
| Results: patient card with trust counts + stats panel, contradictions, fact cards, source and guideline sheets | done |
| Read aloud (Web Speech API, German voices only, prefers on-device voices) | done |
| Übersicht / Verlauf tabs | next |
| Source viewer with the three tracks (dialog-stack), flag form, PDF export, EN/DE toggle | to do |

## Not yet connected to the backend

`src/lib/api.ts` → `fetchPatientBrief(role, task)` is the only place data is fetched; it returns mock
data. The app's data shape (`src/types/fact.ts`: `PatientBrief`, `Fact`, `Contradiction`) does **not**
match the backend's `Briefing` (`frontend/lib/api.ts`, `backend/app/schema.py`): the backend groups
facts under `needs`, uses trust values `consistent | conflicting | stale | single`, returns `findings`
instead of contradictions, cites `segment_ids` instead of excerpt text, and takes one `situation`
string instead of role + task. Connecting needs either a mapping layer in `api.ts` or an agreed shared
schema.

## Layout

```
src/screens/      RoleTaskSelectScreen, LoadingScreen, ResultsScreen, StyleguideScreen (/dev/styleguide, dev only)
src/components/   TaskBar, PatientCard, FactCard, ContradictionCard, Sparkline
src/components/ui/          app-level Button, Card, Badge, Modal, Chip, Icon, Skeleton (use these)
src/components/primitives/  shadcn/ui source the ui/ components wrap
src/theme/theme.css         all color tokens, with measured contrast ratios
src/i18n/strings.ts         every UI string (German), ready for the EN/DE toggle
src/lib/          api (fetch), speech (read aloud), utils
src/types/        fact.ts (data contract), request.ts (screen-to-screen state)
```

UI copy is factual only ("Verifiziert", "Nicht dokumentiert", "Widerspruch"), never advisory.
