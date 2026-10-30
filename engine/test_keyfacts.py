"""Answer-first key facts (engine/keyfacts.py, docs/DECISIONS.md 20).  python3 -m unittest engine.test_keyfacts"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "backend"))

from engine import keyfacts as K  # noqa: E402
from engine.data import store  # noqa: E402
from engine.kb import kb  # noqa: E402
from engine.screen import build_screen  # noqa: E402

CASE1 = ("Pre-operative anaesthesia check. You are the anaesthetist. She is scheduled for a quadrantectomy "
         "(partial removal of the breast) with intraoperative radiotherapy on 16 May 2016.")
CASE2 = "Surgery planning after the tumour board, April 2016. You are the surgeon planning her operation after the tumour board."
CASE3 = "Diabetes review at the GP. You are her general practitioner (GP), reviewing her diabetes in spring 2016."
CASE4 = ("Emergency department at night. You are the emergency physician on night duty. She arrives at 02:00 with "
         "dizziness and blurred vision in the left eye.")
CASE5 = ("Open follow-ups from the 2015 hospital stay. You are her GP. You check which follow-ups from her June 2015 "
         "hospital stay are still open.")


def _card(screen, slot):
    return next(c for c in screen["cards"] if c.get("slot") == slot)


def _labels(line):
    return [it["label_en"] for it in line["items"]]


class KeyFactSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st, cls.k = store(), kb()
        cls.s = {n: build_screen(t, use_llm=False) for n, t in enumerate((CASE1, CASE2, CASE3, CASE4, CASE5), 1)}

    def pick(self, case, slot, terms=""):
        return [it["label_en"] for it in K.select_items(self.st, self.k, _card(self.s[case], slot), K._words(terms),
                                                        "2016-04-15")[0]]

    def test_latest_value_uses_the_needs_own_category(self):  # lvef -> lv_function, not the other echo lines
        self.assertEqual(self.pick(1, "lvef"), ["LVEF 60%, normal systolic LV function"])

    def test_latest_value_takes_the_more_specific_wording_of_the_same_statement(self):
        self.assertEqual(self.pick(2, "cancer_histology"), ["Invasive ductal carcinoma of the breast (left)"])

    def test_latest_key_keeps_one_value_per_receptor(self):
        got = " ".join(self.pick(2, "receptors_ki67"))
        for w in ("Oestrogen", "Progesterone", "HER2", "Ki-67"):
            self.assertIn(w, got)

    def test_current_list_is_the_current_regimen_of_that_class_only(self):
        got = self.pick(3, "med_antidiabetic")
        self.assertEqual(len(got), 3)
        self.assertTrue(all(any(d in x for d in ("Metformin", "Pioglitazone", "Exenatide")) for x in got))
        self.assertEqual(self.pick(4, "med_antihypertensive"), ["Candesartan (Blopress) 16 mg 1-0-1"])  # not 1-0-1/2

    def test_trend_shows_every_value(self):
        self.assertEqual([x.split()[1] for x in self.pick(3, "weight")], ["78", "67", "66"])

    def test_plan_prefers_the_future_planned_item(self):
        self.assertIn("16.05.2016", self.pick(1, "planned_procedure")[0])

    def test_laterality_follows_the_majority_side(self):
        got = self.pick(5, "carotid_stenosis")
        self.assertIn("left", got[0])
        self.assertNotIn("right", " ".join(got))

    def test_event_history_event_plus_cause(self):
        got = self.pick(4, "prior_similar_episode")
        self.assertIn("hypertensive crisis", got[0])
        self.assertTrue(any("attributed" in x for x in got))

    def test_lines_are_short_and_traceable(self):
        for n, s in self.s.items():
            kf = s["key_facts"]
            self.assertLessEqual(len(kf), K.MAX_LINES, n)
            self.assertEqual(kf[0]["kind"], "safety")
            for ln in kf:
                for it in ln["items"]:
                    self.assertTrue(it.get("passages"), (n, it["label_en"]))
                for c in ln["computed"]:
                    self.assertTrue(c["passages"], (n, c["label"]))
                if ln["kind"] == "conflict":
                    self.assertTrue(ln["passages"])
            self.assertLessEqual(sum(ln["kind"] == "not_documented" for ln in kf), 1)

    def test_not_documented_needs_in_one_line(self):
        nd = [ln for ln in self.s[1]["key_facts"] if ln["kind"] == "not_documented"]
        self.assertEqual(len(nd), 1)
        for w in ("Haemoglobin", "Coagulation", "anaesthesia", "Airway"):
            self.assertIn(w, nd[0]["text"])

    def test_safety_line_age_sex_allergy(self):
        ln = self.s[1]["key_facts"][0]
        self.assertEqual(ln["computed"][0]["value"], "57 years")
        self.assertEqual(ln["text"], "female")
        self.assertIn("Contrast media allergy", _labels(ln)[0])

    def test_no_item_twice(self):
        for s in self.s.values():
            ids = [tuple(it["facts"]) for ln in s["key_facts"] for it in ln["items"]]
            self.assertEqual(len(ids), len(set(ids)))

    def test_gated_screens_have_no_key_facts(self):
        self.assertEqual(build_screen("hi", use_llm=False).get("key_facts") or [], [])
        self.assertEqual(build_screen("Firefighter checking the patient", use_llm=False).get("key_facts") or [], [])


class Merge(unittest.TestCase):
    def test_merges_same_group_neighbours_never_drops(self):
        mk = lambda n, g, k=1: K._line("need", [n], n, [{"label_en": n, "facts": [n + str(i)]} for i in range(k)], group=g)
        lines = [mk("a", "Oncology", 3), mk("b", "Oncology"), mk("c", "Oncology"), mk("d", "Medication")]
        out = K._merge(lines, 3)
        self.assertEqual(len(out), 3)
        self.assertEqual(sum(len(x["items"]) for x in out), 6)
        self.assertEqual(out[1]["needs"], ["b", "c"])  # the smallest pair
        self.assertEqual(len(K._merge(lines[2:], 1)), 2)  # different groups: never merged, never dropped


class BriefingContract(unittest.TestCase):
    def test_answer_first_briefing(self):
        from app import adapter
        b = adapter.build_briefing(CASE1)
        self.assertEqual(b.layout, "answer_first")
        seg = adapter.segment_index()
        for ln in b.key_facts:
            for f in ln.facts:
                self.assertTrue(f.segment_ids and all(x in seg for x in f.segment_ids))
        asa = next(f for ln in b.key_facts for f in ln.facts if "Thrombo ASS" in f.label_en)
        self.assertTrue(asa.since and asa.since < asa.date)  # documented since the first letter that lists it
        self.assertTrue(next(n for n in b.needs if n.need == "med_antithrombotic").key)
        self.assertEqual(adapter.build_briefing("hi").key_facts, [])


if __name__ == "__main__":
    unittest.main()
