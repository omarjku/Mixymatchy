"""Readable, trustworthy screen text (rules only, no API key):

  tumour pathology stays out of 'Relevant to your task' for roles it does not guide (the challenge's own
  example: receptor status is left out for the anaesthetist); the allergy card reads as a sentence; an open
  question is not listed beside the finding that answered it; a laterality card leads with its finding,
  not with statement counts.

    python3 -m unittest engine.test_display
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.screen import build_screen  # noqa: E402

HAS_DATA = os.path.exists(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       "data", "build", "facts.json"))
PATHOLOGY = ("receptor", "her2", "ki-67", "histology", "t2 n0")
ANAESTHESIA = ("Pre-operative anaesthesia check. You are the anaesthetist. She is scheduled for a quadrantectomy "
               "(partial removal of the breast) with intraoperative radiotherapy on 16 May 2016.")
EMERGENCY = ("Emergency department at night. You are the emergency physician on night duty. She arrives at 02:00 "
             "with dizziness and blurred vision in the left eye.")


def screen(text):
    return build_screen(text, use_llm=False, detail="short", rulebook="kb")


def card(s, need):
    return next((c for c in (s.get("cards") or []) + (s.get("focus") or []) if c.get("need") == need), None)


def key_text(s):
    return " ".join(" ".join([r.get("text") or ""] + [i["label_en"] for i in r["items"]]) for r in s["key_facts"]).lower()


@unittest.skipUnless(HAS_DATA, "needs data/build (python3 -m pipeline.build)")
class Display(unittest.TestCase):
    def test_no_tumour_pathology_for_anaesthesia(self):
        for q in (ANAESTHESIA, "Anaesthetist, pre-op check before breast surgery",
                  "Physiotherapist, first session after breast surgery"):
            s = screen(q)
            tf = card(s, "task_focus")
            self.assertFalse(tf and any(w in tf["value_en"].lower() for w in PATHOLOGY), q)
            self.assertFalse(any(w in key_text(s) for w in PATHOLOGY), q)

    def test_tumour_pathology_kept_where_it_guides_treatment(self):
        s = screen("Surgery planning after the tumour board, April 2016. You are the surgeon planning her "
                   "operation after the tumour board.")
        self.assertIn("receptor", key_text(s))
        s = screen("GP: what is her receptor status?")  # the request names it: shown for any role
        self.assertIn("receptor", key_text(s))
        from engine.focus import out_of_scope  # the request is about pathology itself: no filter
        import json
        from engine.kb import OVERLAY_PATH
        with open(OVERLAY_PATH, encoding="utf-8") as fh:
            ov = json.load(fh)
        f = {"label_en": "Histology: invasive ductal carcinoma, HER2 negative"}
        self.assertTrue(out_of_scope(ov, "anaesthetist", "pre-op check before breast surgery")(f))
        self.assertFalse(out_of_scope(ov, "physician", "reconstructing the biopsy sample chain")(f))
        self.assertFalse(out_of_scope(ov, None, "pre-op check")(f))

    def test_allergy_reads_as_a_sentence(self):
        c = card(screen(ANAESTHESIA), "allergies")
        self.assertNotIn("||", c["value_en"])
        self.assertNotIn(": found", c["value_en"])
        self.assertTrue(c["value_en"].startswith("Contrast media allergy"))
        self.assertIn("Not documented: drugs (other than contrast)", c["value_en"])
        self.assertTrue(c["checklist"])  # the per-sub-item rows (and their links) are unchanged

    def test_answered_question_not_listed(self):
        s = screen(EMERGENCY)
        for need in ("stroke_tia_hx", "eye_history"):
            labels = [it["label_en"] for it in card(s, need)["items"]]
            self.assertIn("Amaurosis fugax", labels)
            self.assertNotIn("Amaurosis fugax?", labels)
        eye = [it["label_en"] for it in card(s, "eye_history")["items"]]
        self.assertNotIn("Question: hypertensive retinopathy", eye)  # answered: 'Incipient hypertensive retinopathy'
        self.assertIn("Central retinal artery occlusion?", eye)      # nothing answered it: stays

    def test_laterality_leads_with_the_finding(self):
        c = card(screen(EMERGENCY), "carotid_stenosis")
        self.assertTrue(c["value_en"].startswith("Left: Carotid artery stenosis, left, 60%"))
        self.assertNotIn("statement", c["value_en"])
        self.assertEqual(max(c["sides"], key=c["sides"].get), "left")


if __name__ == "__main__":
    unittest.main()
