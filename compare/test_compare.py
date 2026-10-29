"""Tests for compare/: python3 -m unittest compare.test_compare -v  (run from repo root)

Synthetic tests use made-up text only. Real-data tests run against data/build/ when it exists
(they check generic properties and categories, never patient text).
"""
import json
import os
import unittest

from pipeline.common import BUILD_DIR, load_json

from compare.build import validate
from compare.core import compare


# --------------------------------------------------------------------------- synthetic builder
class Synth:
    def __init__(self):
        self.docs, self.passages, self.facts = {}, [], []

    def doc(self, doc_id, date, lines):
        """lines: list of (text, section). Returns passage ids in order."""
        text, pids, pos = "", [], 0
        for i, (line, section) in enumerate(lines):
            pid = "%s:p%04d" % (doc_id, i)
            self.passages.append({"id": pid, "doc_id": doc_id, "section": section, "kind": "line",
                                  "start": pos, "end": pos + len(line), "text": line})
            text += line + "\n"
            pos += len(line) + 1
            pids.append(pid)
        self.docs[doc_id] = {"title": "t", "date": date, "type": "x", "display_text": text}
        return pids

    def fact(self, pid, section, category, label, attrs=None, quote=None, status="historical", date=None, code=None):
        p = next(p for p in self.passages if p["id"] == pid)
        fid = "f%04d" % (len(self.facts) + 1)
        self.facts.append({"id": fid, "ips_section": section, "category": category, "code": code,
                           "label_en": label, "attrs": attrs or {}, "date": date or self.docs[p["doc_id"]]["date"],
                           "date_precision": "day", "status": status, "quote": quote or p["text"],
                           "passage_ids": [pid], "origin": "rule", "verified": True})
        return fid

    def run(self):
        r = compare(self.docs, self.passages, self.facts)
        self.errors = validate(r, self.passages, self.facts)
        return r


def counted(r, kind=None):
    return [c for c in r["contradictions"] if c["tier"] == "counted" and (kind is None or c["kind"] == kind)]


class TestBMI(unittest.TestCase):
    def build(self, h, w, bmi):
        s = Synth()
        p = s.doc("D1", "2020-01-01", [("Height: %s cm" % h, "Vitals"), ("Weight: %s kg" % w, "Vitals"),
                                       ("BMI: %s" % bmi, "Vitals")])
        s.fact(p[0], "vital_signs", "height", "Height", {"value": str(h), "unit": "cm"})
        s.fact(p[1], "vital_signs", "weight", "Weight", {"value": str(w), "unit": "kg"})
        s.fact(p[2], "vital_signs", "bmi", "BMI", {"value": str(bmi)})
        return s

    def test_mismatch_flagged_with_all_three_passages(self):
        s = self.build(180, 70, 30)
        r = s.run()
        c = counted(r, "bmi_mismatch")
        self.assertEqual(len(c), 1)
        self.assertEqual(len(c[0]["claims"]), 3)
        self.assertEqual(s.errors, [])

    def test_within_tolerance_not_flagged(self):
        r = self.build(180, 70, "22,1").run()   # computed 21.6
        self.assertEqual(counted(r, "bmi_mismatch"), [])


class TestLaterality(unittest.TestCase):
    def test_side_conflict_and_copy_hint(self):
        s = Synth()
        a = s.doc("D1", "2020-01-01", [("Left vessel shows a stenosis of about fifty percent here.", "Exam")])
        b = s.doc("D2", "2020-02-01", [("Right vessel shows a stenosis of about fifty percent here.", "Exam"),
                                       ("Summary: stenosis left.", "Summary")])
        s.fact(a[0], "results", "vessel_stenosis", "Stenosis, left", {"side": "left"})
        s.fact(b[0], "results", "vessel_stenosis", "Stenosis, right", {"side": "right"})
        s.fact(b[1], "results", "vessel_stenosis", "Stenosis, left", {"side": "left"})
        r = s.run()
        c = counted(r, "laterality")
        self.assertEqual(len(c), 1)
        self.assertIn("possible copy error", c[0]["rationale"])
        chain = r["propagation"][0]["chain"]
        self.assertEqual([e["status"] for e in chain], ["consistent", "conflicting", "consistent"])
        self.assertEqual(s.errors, [])

    def test_unsided_finding_difference_is_note(self):
        s = Synth()
        a = s.doc("D1", "2020-01-01", [("nodes enlarged right", "Exam")])
        b = s.doc("D2", "2020-01-05", [("no enlarged nodes", "Imaging")])
        s.fact(a[0], "results", "nodes", "Nodes enlarged, right", {"side": "right", "finding": "enlarged"})
        s.fact(b[0], "results", "nodes", "No enlarged nodes", {"finding": "not enlarged"})
        r = s.run()
        self.assertEqual(counted(r), [])
        self.assertEqual([c["kind"] for c in r["contradictions"]], ["laterality_to_check"])

    def test_different_structures_not_compared(self):
        s = Synth()
        a = s.doc("D1", "2020-01-01", [("left ventricle thick", "Echo"), ("right ventricle normal", "Echo")])
        s.fact(a[0], "results", "echo", "Mild left ventricular thickening")
        s.fact(a[1], "results", "echo", "Normal right ventricular function")
        self.assertEqual(counted(s.run()), [])


class TestEvents(unittest.TestCase):
    def test_admission_two_dates_same_doc(self):
        s = Synth()
        p = s.doc("D1", "2020-03-10", [("Admitted 01/03/2020 | Discharged 05/03/2020", "Header"),
                                       ("Admitted to ward on 03.03.2020.", "Course")])
        s.fact(p[0], "past_illness", "encounter", "Stay", {"admission": "01/03/2020", "discharge": "05/03/2020"})
        s.fact(p[1], "past_illness", "encounter", "Admitted", {"event": "admission", "date_text": "03.03.2020"})
        r = s.run()
        self.assertEqual(len(counted(r, "event_date")), 1)

    def test_biopsy_date_from_heading(self):
        s = Synth()
        a = s.doc("D1", "2020-03-04", [("Sampling date: 02.03.2020", "Report")])
        b = s.doc("D2", "2020-03-06", [("Ultrasound of 03.03.2020:", "Ultrasound of 03.03.2020:"),
                                       ("Summary:", "Summary:"), ("A guided biopsy was taken.", "Summary:")])
        s.fact(a[0], "procedures", "biopsy", "Biopsy", {"date_text": "02.03.2020"})
        s.fact(b[0], "procedures", "procedure", "Ultrasound")
        s.fact(b[2], "procedures", "biopsy", "Guided biopsy")
        r = s.run()
        c = counted(r, "event_date")
        self.assertEqual(len(c), 1)
        self.assertIn(b[0], [cl["passage_id"] for cl in c[0]["claims"]])
        self.assertEqual(s.errors, [])

    def test_same_date_and_far_apart_not_flagged(self):
        s = Synth()
        p = s.doc("D1", "2020-03-10", [("Admitted 01/03/2020 | Discharged 05/03/2020", "Header"),
                                       ("Admitted on 01.03.2020.", "Course"), ("Admitted on 01.09.2020.", "Later")])
        s.fact(p[0], "past_illness", "encounter", "Stay", {"admission": "01/03/2020", "discharge": "05/03/2020"})
        s.fact(p[1], "past_illness", "encounter", "Admitted", {"event": "admission", "date_text": "01.03.2020"})
        s.fact(p[2], "past_illness", "encounter", "Admitted", {"event": "admission", "date_text": "01.09.2020"})
        self.assertEqual(counted(s.run()), [])


class TestNoFalseAlarms(unittest.TestCase):
    def test_dose_change_and_weight_change_not_contradictions(self):
        s = Synth()
        a = s.doc("D1", "2020-01-01", [("DrugX 10mg 1 0 1/2 0", "Meds"), ("Weight: 80 kg", "Vitals")])
        b = s.doc("D2", "2021-01-01", [("DrugX 10mg 1 0 1 0", "Meds"), ("Weight: 70 kg", "Vitals")])
        s.fact(a[0], "medications", "antihypertensive", "DrugX 10 mg 1-0-1/2",
               {"generic": "drugx", "dose": "10 mg", "schedule": "1-0-1/2"})
        s.fact(b[0], "medications", "antihypertensive", "DrugX 10 mg 1-0-1",
               {"generic": "drugx", "dose": "10 mg", "schedule": "1-0-1"})
        s.fact(a[1], "vital_signs", "weight", "Weight", {"value": "80"})
        s.fact(b[1], "vital_signs", "weight", "Weight", {"value": "70"})
        r = s.run()
        self.assertEqual(counted(r), [])
        reasons = " ".join(n["reason"] for n in r["not_flagged"])
        self.assertIn("changed over time", reasons)
        wc = [x for x in r["blind_spots"] if x["kind"] == "unstated_computed"]
        self.assertEqual(wc[0]["value"]["delta_kg"], -10.0)


class TestBlindSpotsAndFollowups(unittest.TestCase):
    def test_dropped_problem_and_open_followup(self):
        s = Synth()
        a = s.doc("D1", "2020-01-01", [("Condition A", "Diagnoses"), ("Condition B", "Diagnoses"),
                                       ("Next scan of vessel in 2 months.", "Plan")])
        b = s.doc("D2", "2021-01-01", [("Condition A", "Diagnoses"), ("Scan of knee done", "Findings")])
        s.fact(a[0], "problems", "diagnosis", "Condition A", {"context": "diagnosis list"}, code={"system": "ICD-10", "value": "X1"})
        s.fact(a[1], "problems", "diagnosis", "Condition B", {"context": "diagnosis list"}, code={"system": "ICD-10", "value": "X2"})
        s.fact(a[2], "plan_of_care", "followup", "Follow-up vessel scan in 2 months",
               {"test": "vessel scan", "interval": "2 months"}, status="recommended")
        s.fact(b[0], "problems", "diagnosis", "Condition A", {"context": "diagnosis list"}, code={"system": "ICD-10", "value": "X1"})
        s.fact(b[1], "procedures", "procedure", "Knee scan")
        r = s.run()
        self.assertEqual([x["concept"] for x in r["blind_spots"]], ["ICD-10:X2"])
        self.assertEqual(r["blind_spots"][0]["last_seen_doc"], "D1")
        fu = r["open_followups"][0]
        self.assertEqual(fu["resolution"], "open")
        self.assertEqual(fu["due"], "2020-03-01")
        self.assertTrue(fu["searched"].startswith("searched: categories"))
        self.assertEqual(s.errors, [])


# --------------------------------------------------------------------------- real build (if present)
HAVE_BUILD = all(os.path.exists(os.path.join(BUILD_DIR, n + ".json")) for n in ("docs", "passages", "facts"))


@unittest.skipUnless(HAVE_BUILD, "run python3 -m pipeline.build first")
class TestRealBuild(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = load_json(os.path.join(BUILD_DIR, "docs.json"))
        cls.passages = load_json(os.path.join(BUILD_DIR, "passages.json"))
        cls.facts = load_json(os.path.join(BUILD_DIR, "facts.json"))
        cls.r = compare(cls.docs, cls.passages, cls.facts)
        cls.fact = {f["id"]: f for f in cls.facts}

    def test_claims_valid(self):
        self.assertEqual(validate(self.r, self.passages, self.facts), [])

    def test_at_least_five_counted(self):
        c = counted(self.r)
        self.assertGreaterEqual(len(c), 5)
        kinds = [x["kind"] for x in c]
        self.assertEqual(kinds.count("bmi_mismatch"), 2)
        self.assertEqual(kinds.count("laterality"), 1)
        events = sorted(x["summary_en"].split()[0] for x in c if x["kind"] == "event_date")
        self.assertEqual(events, ["Admission", "Biopsy"])
        lat = next(x for x in c if x["kind"] == "laterality")
        self.assertIn("carotid_stenosis", {self.fact[cl["fact_id"]]["category"] for cl in lat["claims"]})

    def test_every_counted_contradiction_links_two_passages(self):
        for c in self.r["contradictions"]:
            self.assertGreaterEqual(len({cl["passage_id"] for cl in c["claims"]}), 2, c["id"])

    def test_false_alarms_not_counted(self):
        cats = set()
        for c in counted(self.r):
            if c["kind"] != "bmi_mismatch":
                cats |= {self.fact[cl["fact_id"]]["category"] for cl in c["claims"]}
        for bad in ("height", "weight", "blood_pressure", "antihypertensive", "lymph_nodes", "case_number"):
            self.assertNotIn(bad, cats)
        for c in counted(self.r, "bmi_mismatch"):   # BMI mismatches must be within one document
            self.assertEqual(len({cl["doc_id"] for cl in c["claims"]}), 1)

    def test_notes(self):
        notes = {c["kind"] for c in self.r["contradictions"] if c["tier"] == "documentation_note"}
        self.assertIn("laterality_to_check", notes)
        self.assertIn("case_number_mismatch", notes)

    def test_blind_spots(self):
        latest = max(self.docs, key=lambda d: self.docs[d]["date"])
        self.assertEqual(self.r["counts"]["latest_doc"], latest)
        concepts = {x["concept"] for x in self.r["blind_spots"]}
        self.assertIn("ICD-10:G47.3", concepts)           # sleep apnoea
        self.assertIn("cat:carotid_stenosis", concepts)
        self.assertNotIn("ICD-10:K21.9", concepts)        # reflux IS restated (abbreviated) in the latest letter
        for x in self.r["blind_spots"]:
            if x["kind"] == "dropped_from_latest":
                self.assertNotEqual(x["last_seen_doc"], latest)
        self.assertTrue(any(x["kind"] == "unstated_computed" for x in self.r["blind_spots"]))
        self.assertEqual(self.r["counts"]["missed_if_only_latest_read"],
                         sum(x["kind"] == "dropped_from_latest" for x in self.r["blind_spots"]))

    def test_carotid_followup_open(self):
        fu = [f for f in self.r["open_followups"] if "carotid" in f["label_en"].lower()]
        self.assertEqual(len(fu), 1)
        self.assertEqual(fu[0]["resolution"], "open")
        self.assertEqual(fu[0]["evidence"], [])

    def test_propagation_wording(self):
        txt = json.dumps(self.r["propagation"]) + json.dumps(self.r["contradictions"])
        self.assertIn("possible copy error", txt)
        self.assertNotIn("copied wrong", txt)
        for p in self.r["propagation"]:
            dates = [e["date"] for e in p["chain"]]
            self.assertEqual(dates, sorted(dates))
            for e in p["chain"]:
                self.assertIn(e["status"], ("consistent", "conflicting", "absent"))


if __name__ == "__main__":
    unittest.main()
