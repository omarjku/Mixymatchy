# Data contracts (build artefacts)

All build outputs go to `data/build/` (gitignored, never committed: they contain patient text).
Source of truth = document texts in `data/patient-0000-0001/documents/*.json`. IBM JSON = index/hint only.

## Display text
`display_text = html.unescape(raw_text.replace("<BR>", "\n"))` — `<BR>` replaced BEFORE unescaping.
All offsets refer to `display_text`.

## data/build/docs.json
```json
{ "<doc_id>": { "title": "...", "date": "YYYY-MM-DD", "type": "...", "display_text": "..." } }
```

## data/build/passages.json
```json
[{ "id": "<doc_id>:p0042", "doc_id": "...", "section": "nearest heading or null",
   "kind": "line|table_row|sentence", "start": 0, "end": 10, "text": "..." }]
```
Invariant: `docs[doc_id].display_text[start:end] == text` for every passage.

## data/build/facts.json
```json
[{ "id": "f0001",
   "ips_section": "problems|allergies|medications|procedures|results|vital_signs|past_illness|plan_of_care|social_history|functional_status",
   "category": "e.g. antithrombotic|glucose_lowering|antihypertensive|lipid_lowering|bone_agent|vitamin|allergy|lv_function|hba1c|weight|height|bmi|blood_pressure|histology|receptor_status|ki67|tnm|carotid_stenosis|followup|planned_procedure|diagnosis|...",
   "code": { "system": "ATC|ICD-10|MEL", "value": "B01AC06" },
   "label_en": "Acetylsalicylic acid (Thrombo ASS) 100 mg 1-0-0",
   "attrs": { "dose": "100 mg", "schedule": "1-0-0", "value": null, "unit": null, "side": null },
   "date": "2016-04-15", "date_precision": "day|month|year",
   "status": "current|historical|planned|recommended|unknown",
   "quote": "exact substring of display_text",
   "passage_ids": ["12340018:p0071"],
   "origin": "ibm|rule|llm",
   "verified": true }]
```
Rules: every fact's `quote` must be an exact substring of each linked passage's text (after nothing more than whitespace normalisation for matching; stored quote is exact). Every number in `label_en`/`attrs` must appear in the quote unless it is a declared calculated value. JSON-only values (e.g. patient.json age, documents.json admission dates, cave.json) are never facts.

## data/build/eval_report.md
Written by the eval harness: per-question pass/fail, invariant violations, gaps.
