# Integration: backend + mobile frontend

> Owners: Omar (backend: `pipeline/`, `compare/`, `engine/`, `backend/app/`), Zoha (frontend: `mobile/`),
> Mani (routing knowledge base: `rulebook/kb/`). The contract is `backend/app/schema.py`;
> `docs/contract/*.example.json` are complete examples with **invented** data for mocks and shape tests.

## 1. How the pieces connect

```
data/ (8 letters, git-ignored)
  └─ pipeline/  ── facts with verbatim quotes ──┐
     compare/   ── contradictions, blind spots ─┤  data/build/ (git-ignored)
rulebook/kb/routing_knowledge_base.json ────────┤  (Mani: roles, bundles B01–B18, slots, P1–P3, rules, guidelines)
                                                ▼
engine/ (route → fill)  →  backend/app/adapter.py  →  FastAPI  POST /briefing, GET /documents/{id}
                                                               ▼
mobile/src/lib/backend.ts  (fetch + map to PatientBrief)  →  mobile screens
```

- **Backend default:** deterministic engine with Mani's knowledge base as rulebook. `SECOND_LOOK_RULEBOOK=legacy` falls back to `rulebook/roles.json`; `SECOND_LOOK_LLM=1` (+ `ANTHROPIC_API_KEY`) enables the LLM parser for unusual wording.
- **Frontend:** `mobile/src/lib/api.ts` calls the backend by default; `VITE_MOCK=1` uses the invented mock briefs (never for the demo).
- **Dev:** the Vite dev server proxies `/briefing`, `/documents`, `/segments`, `/health` to `BACKEND_URL` (default `http://127.0.0.1:8000`), so the app also works from a phone on the LAN. In deployment FastAPI serves the built app, so the same relative paths work.

## 2. Run it end to end

```bash
# repo root, data/ present
make build                                              # pipeline + compare -> data/build/
python -m uvicorn --app-dir backend app.main:app --port 8000
cd mobile && npm ci && npm run dev                      # http://localhost:5173
```

## 3. Contract (backend/app/schema.py) and how the app maps it

| Backend field | App (`PatientBrief`) | Screen |
|---|---|---|
| `POST /briefing {situation, detail}` | role chip English name + ", " + task; "Andere Rolle" sends the typed text alone; `detail: "short"` (P1) | — |
| `needs[].facts[]` (`label_en`, `value`, `unit`, `segment_ids`, `trust`) | `Fact` per backend fact, label = need label | fact card |
| `trust`: consistent / single → `verified`; conflicting → `conflicting`; stale → `outdated` | `FactTrust` | badge (icon + text) |
| `needs[].status = not_documented`, `note` | `Fact` with `trust: not_documented`, note | "Nicht dokumentiert" + what was searched |
| `needs[].status = not_applicable`, `reason`, `reason_segment_ids` | value "Nicht zutreffend: …" with its source | fact card |
| `needs[].computed[]` (`label`, `value`, `formula`, `segment_ids`) | `Fact` with `computed: true`, note = formula | "Berechnet: …" |
| `shape: trend` with ≥ 2 numeric facts | one `Fact` with `history` | Verlauf tab |
| `needs[].why` + `sources[0]` | `guideline` (name, why, url) | "Leitlinie" sheet = why this is shown |
| `findings[kind=conflict]` + `tier` | `Contradiction` with `tier`, `explanation` | counted contradictions first; documentation notes after the facts |
| `findings[kind=dropped / followup / silence]` | `RecordGap` | "Offen im Verlauf" after the facts |
| `segment_ids` → `GET /documents/{id}` (cached per session) | `SourceCitation {documentLabel, excerpt}` | source sheet shows the exact passage |
| `stats` | `stats` | counts are never typed in |
| `routing.fallback_note`, `routing.anchor_date` | `routeNote`, `generatedAt` | fallback notice; "Stand" = latest document date |

Needs with more than 20 facts show the first 8 and one "N weitere Einträge" row (all remaining passages stay linked). None of the five demo situations has a need with more than 15 facts.

Not yet used by the app (available from the backend): `checklist[]`, `label_panel[]`, `rules[]`, `priority` P2/P3 (long mode), `blind_spot[]` as facts. See docs/FRONTEND.md for the planned UI.

## 4. Integration test results (30.10.2026, local)

| Check | Result |
|---|---|
| Backend unit tests (compare 18, engine 8, kb 20, eval 30, backend 27) + security | all pass |
| `python -m eval.run --strict` | 15/15, 0 invariant violations |
| HTTP eval, detail short / long | 15/15 / 15/15; slowest 115 ms / 144 ms |
| UI, 5 situations: every expected answer visible without clicking | 5/5, slowest 453 ms (submit → facts rendered) |
| UI, 15 unseen situations (`eval/unseen_situations.json`) via "Andere Rolle" | 15/15 render, 0 console errors, ≤ 0.5 s |
| `npm run build` | passes (existing chunk-size warning) |

## 5. Open items

**Backend (Omar)**
1. `diagnoses_all` returns every mention (55 facts): merge mentions of the same diagnosis across letters.
2. Routing gaps without the LLM parser: "Dietitian reviewing her weight" and "GP checking her HbA1c" fall back to B18 (tags miss "weight", "HbA1c"); "Rheumatologist" is not one of the 20 roles. Enable `SECOND_LOOK_LLM=1` in the deployment and add tags/roles.
3. Explanations expose internals ("searched: categories allergies, functional_status, … terms [caro, dupl, ultr]", "check X02"): keep the clinician-facing sentence, move the search detail to a separate field.
4. Optional: `POST /segments {ids}` (fewer requests), English translation per segment, propagation chains in the API for the "how this fact travelled" view.
5. Docker: serve `mobile/dist` instead of `frontend/out`.

**Frontend (Zoha)** — design and features in docs/FRONTEND.md
1. English default UI (the jury writes in English; backend labels are English, UI strings German today).
2. Short / Full toggle (`detail`), P2/P3 sections, `checklist[]` items, label panels in Full mode only.
3. Inline serif quote under each fact and the highlighted passage in letter context (annotated-letter design).
4. Dashboard: no stats endpoint yet, so it shows nothing in real mode (mock numbers only with `VITE_MOCK=1`).

## 6. Merge order
1. Omar merges his branch (`claude/peaceful-ride-nw0xm5`) to `main`.
2. Zoha merges `mobile-frontend` plus the integration changes (`mobile/src/lib/backend.ts` and the small component changes listed in the integration commit).
3. Re-run §4 on `main`; tag `demo-v1` for the video.
