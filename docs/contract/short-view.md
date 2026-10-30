# Short view API shape (for the mobile app)

`POST /briefing {"situation": "...", "detail": "short"}` returns one `Briefing` (backend/app/schema.py).
No second request is needed to show the "Also relevant" section.

| Field | Meaning |
|---|---|
| `needs[]` with `priority: "P1"` | main screen. The first two are always the **safety core**: `slot: "age_sex"` and `slot: "allergies"` (every clinical screen, short and long). |
| `needs[]` with `priority: "P2"` | the **Also relevant** group (decision 4). Ordered after all P1 needs; at most 5, documented ones first. |
| `routing.also_relevant` | the `need` ids of that group, in display order (same as the P2 needs). |
| `routing.also_relevant_more` | how many further P2 needs exist (shown with `detail: "long"`). |
| `routing.role_label` | role as recognised. Unknown clinical roles keep their own word (e.g. "Nephrologist"), never "GP". |
| `routing.fallback_note` | visible note when the task wording was not recognised (e.g. "showing what a Urologist usually needs"). |
| `routing.screen_mode` | `task`, `fallback` (safety summary), `overview`, `sex_specific`, `not_applicable`, `not_authorised`. |
| `needs[].facts[].value` / `unit` | filled for every numeric fact (weight, height, BMI, blood pressure "128/80", heart rate, HbA1c, LVEF, Ki-67, receptor %, tumour size, stenosis %). The number is always also in the source quote. Use them for the History tab. |
| `findings[].title` | readable: letter type + date, never passage ids (e.g. "Carotid stenosis: discharge letter 28.06.2015 says RIGHT; radiology report 11.06.2015 and 10 other passage(s) say LEFT"). |

With `detail: "long"` there is no `also_relevant` group: P1, P2 and P3 needs are all returned in priority order.

Example (shape only):

```json
{"needs": [{"need": "age_sex", "priority": "P1"}, {"need": "allergies", "priority": "P1"},
           {"need": "hba1c", "priority": "P1", "facts": [{"label_en": "HbA1c 6.4%", "value": "6.4", "unit": "%"}]},
           {"need": "vitals_bp_hr", "priority": "P2"}],
 "routing": {"also_relevant": ["vitals_bp_hr"], "also_relevant_more": 3, "role_label": "General practitioner"}}
```
