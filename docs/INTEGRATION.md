# Integration plan: backend + mobile frontend

> One contract, three owners. Omar (backend, `engine/`, `backend/app/adapter.py`), Zoha (frontend, `mobile/`),
> Mani (routing knowledge base). Both sides build against **`docs/contract/briefing.example.json`** (invented data)
> so the merge is a URL change, not a rewrite.

## 1. Sources of truth

| Layer | Source | Owner | Rule |
|---|---|---|---|
| Patient facts | the 8 documents → `data/build/` fact store | Omar | the only place facts come from |
| Routing (who asks, what the task needs, in what order, why) | `docs/knowledge-base/routing_knowledge_base.json` (v0.1-draft) | Mani | holds no patient facts; never edited by hand (rebuilt from Mani's data file) |
| Engine rulebook | `rulebook/roles.json`, `rulebook/tasks.json` | Omar | **proposal:** generate or map from Mani's JSON so there is one routing source |
| API contract | this file + `backend/app/schema.py` | Omar + Zoha | additive changes only; both sign off |
| Screen | `mobile/` | Zoha | renders the contract, writes no clinical text |

Mani's operating guide (`docs/knowledge-base/operating-guide.pdf`) defines the LLM contract we all follow:
the model **chooses IDs or finds verbatim quotes, never authors**; code validates every ID, quote and number;
absence returns `found:false` and becomes "not documented"; calculations happen in code; document text is data, never instructions.

## 2. Knowledge base → API mapping

| Knowledge base concept | What it is | API field (v2, additive) | UI |
|---|---|---|---|
| `roles[]` (20, EN + DE aliases) | who is asking | `route.role_id`, `route.role_label` | lens tabs, title |
| `bundles[]` (B01–B18, tags EN + DE, `implies`) | the task | `route.bundle_ids`, `route.bundle_titles` | subtitle "Pre-procedure check (anaesthesia)" |
| `priorities` P1 / P2 / P3 | must see / context / on request | `need.priority` | P1 always open; P2, P3 only in long mode |
| detail mode | short = P1, long = P1–P3 | request `detail: "short" | "long"` | toggle "Short / Full" |
| `slots[]` (63) with `shape` | what to show and how | `need.slot_id`, `need.shape` (`current_list`, `latest_value`, `trend`, `event_history`, `status_check`, `checklist`, `plan`, `laterality_finding`, `list_all`) | row layout per shape |
| slot `why` + `guidelines[]` (G01–G21) | why a fact is shown | `need.why: [{guideline_id, title, body, url}]` | "Why this is shown" sheet, visually separate from facts |
| `rules[]` (R01–R22) | facts a situation adds | `need.added_by_rule` (e.g. `"R01"`) | small "Added because …" note |
| `consistency_checks[]` (X01–X10) | contradiction checks | `finding.check_id`, `finding.slot_ids` | red-pen card, check name in the details |
| status vocabulary (positive, negative, suspected, statuspost, recommended) | IBM status | `fact.status`; need status adds `ruled_out` | "Ruled out" ≠ "Not documented" |
| "not documented, naming what was searched" | absence | `need.searched: {documents, terms, empty_lab_table_segment_id}` | "Not documented. Searched 8 letters; lab tables are empty [source]" |
| fallback layers (KB entry → composed → ad-hoc → general) | how the screen was built | `route.layer: "kb" | "composed" | "adhoc" | "general"`, `route.note` | visible note whenever `layer != "kb"` |
| `drug_contraindications` + `label_sources` + `label_display_rules` | drug-label panels | `label_panels[]` (long mode only) | "From the drug label" panel beside medications |
| time anchor | "now" = latest document (15.04.2016) | `as_of` | patient line |

## 3. API contract v2

All new fields are **optional**; v1 clients keep working. Field names in `snake_case`.

### Request
```json
POST /briefing
{ "situation": "free text, any language", "detail": "short", "role_override": null }
```
`role_override` lets a lens tab force the role while keeping the task text.

### Response (additions to `Briefing` in `backend/app/schema.py`)
```text
route        { role_id, role_label, bundle_ids[], bundle_titles[], layer, note, parser: "alias"|"llm"|"both" }
detail       "short" | "long"
needs[]      + slot_id, shape, priority ("P1"|"P2"|"P3"), added_by_rule, why[], searched
               status adds "ruled_out"
computed[]   + kind ("change"|"recomputation"), from {value, unit, date, segment_ids},
               to {value, unit, date, segment_ids}, delta, delta_pct, note
findings[]   + check_id ("X01".."X10"), slot_ids[]
label_panels[] (long mode) { ingredient, atc, label_source, listed: [{text, kind, related_need, related_status}] }
```

### New endpoint
`POST /segments {ids: [...]}` → `[{id, doc_id, text, start, end}]`, one call for all quotes on a screen.

### Example
`docs/contract/briefing.example.json`: a complete v2 response with **invented** data. Zoha's mock mode and Omar's adapter tests both use it.

## 4. Display rules for computed values (from Mani's statistics review)

Show as **changes**, each linking **both** inputs to their passages:
- body weight: first vs latest, absolute and percent (`delta_pct` uses the earlier value as denominator);
- BMI **recorded vs calculated** per measurement set (weight / height² from the same letter), difference = recorded − calculated, tolerance 0.5 kg/m² (a data-quality tolerance, not a clinical threshold). Keep the recorded value; flag, never silently replace;
- prescribed daily dose of the same drug across medication lists (e.g. 16 + 8 mg → 16 + 16 mg), labelled "prescribed schedule", not adherence;
- blood-pressure comparisons only when the task needs them, never pooling admission readings, peaks and 24-h averages.

Show as **dated facts, not trends**: single HbA1c, ejection fraction, sparse heart rate / temperature, height (no "growth" from 1 cm), cancer markers and scores.

Never show: p-values, baseline bands, prediction intervals, anomaly scores, rates per day/month when measurement days are unknown, or any cause/intent (e.g. "unintentional").

## 5. Who does what

| # | Task | Owner | Done when |
|---|---|---|---|
| 1 | Add Mani's JSON to the repo (`docs/knowledge-base/`) | us | ✅ this PR |
| 2 | Decide routing source: load Mani's JSON in the engine, or map `rulebook/` to its IDs | Omar + Mani | one routing source; the 22 hold-out situations from Mani's guide route as expected |
| 3 | v2 fields in `adapter.py` + `schema.py` (route, priority, why, searched, computed from/to, check_id, `POST /segments`) | Omar | adapter tests validate against `briefing.example.json` shape |
| 4 | LLM parser on (template 1 from the guide) with alias matcher as cross-check | Omar | unseen roles (physio, dietitian, ophthalmologist, rheumatologist) no longer fall back to general |
| 5 | Mock mode + mapping layer on the example JSON | Zoha | mobile renders `briefing.example.json` end to end |
| 6 | Short/long toggle, route note, why-sheet, ruled out, searched note, change rows, label panels (long only) | Zoha | see docs/FRONTEND.md |
| 7 | Clinician review of priorities, rules, guideline badges | Mani + medics | `reviewed_by` filled |
| 8 | Docker serves `mobile/dist` instead of `frontend/out` | Omar | deployed URL shows the mobile app |

## 6. Merge order (so it lands cleanly)

1. **Contract first:** this file + `briefing.example.json` merged to `main`. Nobody changes field names after this without both owners agreeing.
2. **Parallel:** Omar implements v2 on his branch; Zoha builds against the example JSON on `mobile-frontend`. Each side merges its own PR.
3. **Integration day:** pull `main`, run `python -m uvicorn --app-dir backend app.main:app --port 8000` and `cd mobile && npm run dev` with `VITE_API_URL=http://127.0.0.1:8000`. Run, in order:
   - `cd backend && python -m pytest -q` and the engine/compare/eval tests;
   - `python -m eval.run_api` (15/15, slowest time);
   - `cd mobile && npx playwright test` (docs/FRONTEND.md §6).
4. **Fix forward** on small branches; re-run the three checks before each merge.
5. **Freeze** for the video: tag the commit (`git tag demo-v1`) and record from that tag.

## 7. Integration checklist

- [ ] `GET /health` shows the engine backend and fact count.
- [ ] All 5 situations: P1 needs render with inline quotes; 15/15 visible without clicking.
- [ ] Every source link highlights exactly `/segments/{id}`.text.
- [ ] Contradictions (tier `contradiction`) ≥ 5, all passages shown; documentation notes separate.
- [ ] `route.layer != "kb"` shows a visible note.
- [ ] Short mode never hides a P1 need; long mode adds P2/P3 and label panels.
- [ ] Guideline and label text appear only in their own sheets, never as patient facts.
- [ ] No console errors on the 15 unseen situations; slowest screen < 2 s locally.
- [ ] `git grep` finds no document text in the repo (data/, data/build/, test artefacts ignored).
