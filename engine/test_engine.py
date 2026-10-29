"""Engine tests:  python3 -m unittest engine.test_engine -v

* The 5 case situations (title + description only, never the questions) must
  show each of the 15 expected answers in the screen's cards, using the token
  logic of eval/answer_keys.json applied to what the screen shows (English
  label of each displayed fact, plus its date) and linked to a source document.
* 8 unseen situations must produce sensible, non-empty screens.
* Every screen must build in under 1 second.
"""
import json
import os
import time
import unittest

from eval.core import Build, attrs_text, eval_question, norm

from engine.data import ROOT, store
from engine.screen import build_screen

SITUATIONS = {
    "1": "Pre-operative anaesthesia check. You are the anaesthetist. She is scheduled for a quadrantectomy "
         "(partial removal of the breast) with intraoperative radiotherapy on 16 May 2016.",
    "2": "Surgery planning after the tumour board, April 2016. You are the surgeon planning her operation "
         "after the tumour board.",
    "3": "Diabetes review at the GP. You are her general practitioner (GP), reviewing her diabetes in spring 2016.",
    "4": "Emergency department at night. You are the emergency physician on night duty. She arrives at 02:00 "
         "with dizziness and blurred vision in the left eye.",
    "5": "Open follow-ups from the 2015 hospital stay. You are her GP. You check which follow-ups from her "
         "June 2015 hospital stay are still open.",
}

UNSEEN = [
    # (text, expected role, a task that must be selected, must-have checks)
    ("Medication review. You are the clinical pharmacist reviewing her discharge medication for interactions "
     "and dosing.", "pharmacist", "med_review", {"current_meds": "consistent", "renal_function": "not_documented"}),
    ("Adjuvant therapy decision. You are the oncologist planning adjuvant endocrine therapy after her breast "
     "surgery.", "oncologist", "endocrine_therapy",
     {"receptor_status": "consistent", "menopausal_status": "not_documented", "osteoporosis": "consistent"}),
    ("Vascular consult. You are the vascular surgeon asked to assess her carotid artery disease.",
     "vascular_surgeon", "carotid_review", {"carotid": "conflicting", "carotid_duplex_done": "not_documented"}),
    ("CT angiography request. You are the radiologist; a contrast-enhanced CT of the neck vessels is requested.",
     "radiologist", "contrast_imaging", {"allergy": "consistent", "metformin": "consistent",
                                        "renal_function": "not_documented"}),
    ("Cardiology consult before surgery. You are the cardiologist assessing her pre-operative cardiac risk "
     "before the breast operation.", "cardiologist", "cardiac_risk",
     {"lvef": "outdated", "functional_capacity": "not_documented"}),
    ("Nursing admission. You are the ward nurse admitting her to the surgical ward on 15 May 2016.",
     "nurse", "nursing_admission", {"allergy": "consistent", "weight": "consistent"}),
    ("Prostate check. You are her GP doing a prostate cancer screening examination with PSA.",
     "gp", "prostate_screening", {"psa": "not_applicable", "prostate_exam": "not_applicable"}),
    ("Endocrinology consult. You are the endocrinologist reviewing her diabetes and her osteoporosis.",
     "endocrinologist", "diabetes_review", {"diabetes_meds": "consistent", "bone_agent": "consistent",
                                            "bone_density": "not_documented"}),
]


def card_facts(screen):
    """Fact ids displayed in the cards (items, earlier values, related recommendations)."""
    ids = []
    for c in screen["cards"]:
        for it in (c.get("items") or []) + (c.get("earlier") or []) + (c.get("related") or []):
            for e in [it] + (it.get("earlier") or []):
                for x in e.get("facts") or []:
                    if x not in ids:
                        ids.append(x)
    return ids


def card(screen, need):
    return next((c for c in screen["cards"] if c["need"] == need), None)


class TestCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "eval", "answer_keys.json"), encoding="utf-8") as fh:
            cls.keys = json.load(fh)
        cls.st = store()
        cls.screens = {}
        for sid, text in SITUATIONS.items():
            t0 = time.perf_counter()
            cls.screens[sid] = build_screen(text, use_llm=False)
            cls.screens[sid]["_wall"] = time.perf_counter() - t0

    def _shown_build(self, screen):
        facts = [self.st.fact_by_id[x] for x in card_facts(screen)]
        b = Build(self.st.docs, self.st.passages, facts)
        texts = {f["id"]: norm((f.get("label_en") or "") + " | " + attrs_text(f.get("attrs") or {}))
                 for f in facts}
        return b, texts

    def test_15_answers(self):
        failures = []
        for qid in sorted(k for k in self.keys if not k.startswith("_")):
            sid = qid.split(".")[0]
            b, texts = self._shown_build(self.screens[sid])
            res = eval_question(b, qid, self.keys[qid], texts)
            if not res["pass"]:
                failures.append((qid, [(i["name"], i["missing"]) for i in res["items"] if not i["pass"]],
                                 res["forbidden_hits"]))
        self.assertEqual(failures, [], "questions not answered on screen: %r" % failures)

    def test_not_documented_answers(self):
        self.assertEqual(card(self.screens["4"], "renal_function")["status"], "not_documented")
        duplex = card(self.screens["5"], "carotid_duplex_done")
        self.assertEqual(duplex["status"], "not_documented")
        self.assertTrue(duplex["related"], "the recommendation it was checked against is shown")

    def test_roles_and_filtering(self):
        u = {sid: s["understood"] for sid, s in self.screens.items()}
        self.assertEqual(u["1"]["role_id"], "anaesthetist")
        self.assertEqual(u["2"]["role_id"], "surgeon")
        self.assertEqual(u["3"]["role_id"], "gp")
        self.assertEqual(u["4"]["role_id"], "emergency_physician")
        self.assertEqual(u["5"]["role_id"], "gp")
        # the anaesthetist does not get the tumour's receptor status; the surgeon does
        self.assertIsNone(card(self.screens["1"], "receptor_status"))
        self.assertIsNotNone(card(self.screens["2"], "receptor_status"))

    def test_statuses(self):
        self.assertEqual(card(self.screens["1"], "lvef")["status"], "outdated")
        w = card(self.screens["3"], "weight_change")
        self.assertEqual(w["calculated"]["change"], -12)
        self.assertEqual(card(self.screens["4"], "antihypertensives")["items"][0]["label_en"],
                         "Candesartan (Blopress) 16 mg 1-0-1")

    def test_proof_bar_and_speed(self):
        for sid, s in self.screens.items():
            pb = s["proof_bar"]
            self.assertGreater(pb["facts_shown"], 0)
            self.assertEqual(pb["facts_shown"], pb["facts_verified"])
            self.assertLess(s["_wall"], 1.0, "situation %s took %.2fs" % (sid, s["_wall"]))
            for c in s["cards"]:
                if c["status"] not in ("not_documented", "not_applicable"):
                    self.assertTrue(c["facts"] and c["passages"], "card %s has no source link" % c["need"])


class TestUnseen(unittest.TestCase):
    def test_unseen_situations(self):
        for text, role, task, checks in UNSEEN:
            with self.subTest(role=role):
                t0 = time.perf_counter()
                s = build_screen(text, use_llm=False)
                self.assertLess(time.perf_counter() - t0, 1.0)
                u = s["understood"]
                self.assertEqual(u["role_id"], role, text)
                self.assertIn(task, u["task_ids"], text)
                self.assertGreaterEqual(len(s["cards"]), 3)
                self.assertTrue(any(c["status"] not in ("not_documented", "not_applicable") for c in s["cards"])
                                or role == "gp")
                for need, status in checks.items():
                    c = card(s, need)
                    self.assertIsNotNone(c, "%s: card %s missing" % (role, need))
                    self.assertEqual(c["status"], status, "%s: %s -> %s" % (role, need, c["value_en"]))

    def test_other_role_fallback(self):
        s = build_screen("I am a physiotherapist seeing her after the operation.", use_llm=False)
        self.assertEqual(s["understood"]["role_id"], "other")
        self.assertTrue(s["cards"])

    def test_fuzzy_role(self):
        s = build_screen("anesthesiologst here, pre-op visit", use_llm=False)
        self.assertEqual(s["understood"]["role_id"], "anaesthetist")


if __name__ == "__main__":
    unittest.main()
