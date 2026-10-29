"""Generate a tiny SYNTHETIC fixture (invented text, fictional patient).

    python3 -m eval.fixtures.make_fixture

Writes eval/fixtures/raw/ (IBM-style inputs) and eval/fixtures/build/
(docs/passages/facts per docs/contracts.md).  Nothing here is taken from the
challenge documents.
"""
import json
import os

from eval.core import display_text_from_raw

HERE = os.path.dirname(os.path.abspath(__file__))

RAW_DOCS = {
    "90000001": {
        "title": "Entlassungsbrief", "date": "2020-01-10", "type": "Arztbrief",
        "text": "Entlassungsbrief<BR>Aufnahme am 03/01/2020 | Entlassen am 09/01/2020<BR><BR>"
                "Allergien:<BR>Penicillin-Allergie (Exanthem)<BR><BR>"
                "Größe: 180 cm<BR>Gewicht: 90 kg<BR>BMI: 31,5<BR><BR>"
                "Entlassungsmedikation:<BR>Ramipril 5mg oral 1 0 0 0 ST<BR>"
                "Metoprolol 47,5mg oral 1 0 1/2 0 ST<BR><BR>"
                "Procedere:<BR>Kontrolle beim Hausarzt in 4 Wochen &amp; Laborkontrolle.",
    },
    "90000002": {
        "title": "Ambulanzbrief", "date": "2020-03-02", "type": "Ambulanzbrief",
        "text": "Ambulanzbrief<BR>Gewicht: 85 kg<BR>Medikation: Metoprolol 47,5mg 1 0 1 0<BR>"
                "Echo: EF 55%, Befund &gt; Vorbefund unverändert.",
    },
}

# fact spec: (id, doc, line text (passage), quote, label, extra fields)
FACTS = [
    ("f01", "90000001", "Penicillin-Allergie (Exanthem)", "Penicillin-Allergie (Exanthem)",
     "Penicillin allergy (rash)", {"ips_section": "allergies", "category": "allergy"}),
    ("f02", "90000001", "Ramipril 5mg oral 1 0 0 0 ST", "Ramipril 5mg oral 1 0 0 0 ST",
     "Ramipril 5 mg 1-0-0", {"ips_section": "medications", "category": "antihypertensive",
                             "attrs": {"dose": "5 mg", "schedule": "1-0-0"}}),
    ("f03", "90000001", "Metoprolol 47,5mg oral 1 0 1/2 0 ST", "Metoprolol 47,5mg oral 1 0 1/2 0 ST",
     "Metoprolol 47.5 mg 1-0-1/2", {"ips_section": "medications", "category": "antihypertensive",
                                    "status": "historical"}),
    ("f04", "90000002", "Medikation: Metoprolol 47,5mg 1 0 1 0", "Metoprolol 47,5mg 1 0 1 0",
     "Metoprolol 47.5 mg 1-0-1", {"ips_section": "medications", "category": "antihypertensive"}),
    ("f05", "90000001", "Größe: 180 cm", "Größe: 180 cm", "Height 180 cm",
     {"ips_section": "vital_signs", "category": "height", "attrs": {"value": 180, "unit": "cm"}}),
    ("f06", "90000001", "Gewicht: 90 kg", "Gewicht: 90 kg", "Weight 90 kg",
     {"ips_section": "vital_signs", "category": "weight", "attrs": {"value": 90, "unit": "kg"}}),
    ("f07", "90000001", "BMI: 31,5", "BMI: 31,5", "BMI 31.5",
     {"ips_section": "vital_signs", "category": "bmi", "attrs": {"value": 31.5}}),
    ("f08", "90000002", "Gewicht: 85 kg", "Gewicht: 85 kg", "Weight 85 kg",
     {"ips_section": "vital_signs", "category": "weight", "attrs": {"value": 85, "unit": "kg"}}),
    ("f09", "90000002", "Echo: EF 55%, Befund > Vorbefund unverändert.", "EF 55%",
     "LVEF 55%", {"ips_section": "results", "category": "lv_function"}),
    ("f10", "90000001", "Kontrolle beim Hausarzt in 4 Wochen & Laborkontrolle.",
     "Kontrolle beim Hausarzt in 4 Wochen & Laborkontrolle.", "GP check in 4 weeks and lab check",
     {"ips_section": "plan_of_care", "category": "followup", "status": "recommended"}),
    ("f11", "90000001", "Aufnahme am 03/01/2020 | Entlassen am 09/01/2020", "Aufnahme am 03/01/2020",
     "Admission 03.01.2020", {"ips_section": "past_illness", "category": "admission",
                              "date": "2020-01-03"}),
]

KEYS = {
    "F1": {"question": "Which allergy?", "sources": ["90000001"],
           "items": [{"name": "penicillin allergy with rash",
                      "groups": [["penicillin"], ["allerg"], ["exanthem", "rash"]]}]},
    "F2": {"question": "Current beta blocker dose?", "sources": ["90000002"],
           "items": [{"name": "metoprolol 47.5 mg 1-0-1",
                      "groups": [["metoprolol"], ["47,5 mg"], ["1-0-1", "1 0 1 0"]]}]},
    "F3": {"question": "Weight change?", "sources": ["90000001", "90000002"],
           "items": [{"name": "90 kg", "sources": ["90000001"], "groups": [["weight"], ["90kg"]]},
                     {"name": "85 kg", "sources": ["90000002"], "groups": [["weight"], ["85 kg"]]}]},
    "F4": {"question": "Was the follow-up lab check done?", "mode": "not_documented", "sources": [],
           "items": [{"name": "lab check recommended", "sources": ["90000001"],
                      "groups": [["laborkontroll", "lab check"]]}],
           "forbid": {"why": "would claim the lab check happened",
                      "groups": [["lab", "labor"]], "date_after": "2020-01-09",
                      "ignore_status": ["recommended", "planned"]}},
}


def build():
    docs, passages, facts = {}, [], []
    for did, d in RAW_DOCS.items():
        dt = display_text_from_raw(d["text"])
        docs[did] = {"title": d["title"], "date": d["date"], "type": d["type"], "display_text": dt}
        pos, n = 0, 0
        for line in dt.split("\n"):
            if line.strip():
                n += 1
                passages.append({"id": "%s:p%04d" % (did, n), "doc_id": did, "section": None,
                                 "kind": "line", "start": pos, "end": pos + len(line), "text": line})
            pos += len(line) + 1
    for fid, did, ptext, quote, label, extra in FACTS:
        pid = next(p["id"] for p in passages if p["doc_id"] == did and p["text"] == ptext)
        f = {"id": fid, "ips_section": "problems", "category": "", "code": None,
             "label_en": label, "attrs": {}, "date": docs[did]["date"], "date_precision": "day",
             "status": "current", "quote": quote, "passage_ids": [pid], "origin": "rule",
             "verified": True}
        f.update(extra)
        facts.append(f)
    return docs, passages, facts


def raw_files():
    documents = {"documents": [{"id": did, "title": d["title"], "date": d["date"],
                                "admission": {"admission": {"date": "2020-01-04"},
                                              "discharge": {"date": "2020-01-08"}}}
                               for did, d in RAW_DOCS.items()]}
    patient = {"id": "x", "name": "Max Testmann", "age": 44, "dateOfBirth": "1980-02-02"}
    cave = {"diagnoses": [], "adverseReactions": [{"text": "Arzneimittel-Allergie", "conceptIds": []}]}
    return documents, patient, cave


def write(base=HERE):
    docs, passages, facts = build()
    documents, patient, cave = raw_files()
    os.makedirs(os.path.join(base, "build"), exist_ok=True)
    os.makedirs(os.path.join(base, "raw", "documents"), exist_ok=True)
    for name, obj in (("docs.json", docs), ("passages.json", passages), ("facts.json", facts)):
        with open(os.path.join(base, "build", name), "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=1)
    for did, d in RAW_DOCS.items():
        with open(os.path.join(base, "raw", "documents", did + ".json"), "w", encoding="utf-8") as fh:
            json.dump({"metadata": {"id": did, "date": d["date"]}, "text": d["text"]}, fh,
                      ensure_ascii=False, indent=1)
    for name, obj in (("documents.json", documents), ("patient.json", patient), ("cave.json", cave)):
        with open(os.path.join(base, "raw", name), "w", encoding="utf-8") as fh:
            json.dump(obj, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(base, "answer_keys.json"), "w", encoding="utf-8") as fh:
        json.dump(KEYS, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    write()
    print("fixture written to", HERE)
