"""Specific questions (engine/ask.py, routing guide layer 3) and plan/status accuracy (rules only, no API key):

  a question about one thing is answered with its facts or passages, or 'Nothing found' naming what was
  searched; a question that names no task does not get the role's whole default view; past plans and plans
  from later letters stay off the planned-procedure card; 'recommended' never claims 'not done'.

    python3 -m unittest engine.test_ask

Wordings here are invented for these tests; they are not taken from any eval set.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ask as Q  # noqa: E402
from engine.screen import build_screen  # noqa: E402

HAS_DATA = os.path.exists(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       "data", "build", "facts.json"))


def screen(text, as_of=None):
    return build_screen(text, as_of=as_of, use_llm=False, detail="short", rulebook="kb")


def question_cards(s):
    return [c for c in s.get("focus") or [] if c.get("group") == "question"]


class Subjects(unittest.TestCase):
    def test_question_subjects(self):
        self.assertEqual(Q.subjects(": does she have a pacemaker?"), ["pacemaker"])
        self.assertEqual(Q.subjects(": did she ever have a fall?"), ["fall"])
        self.assertEqual(Q.subjects(": what is her blood type?"), ["blood type"])
        self.assertEqual(Q.subjects(": any history of thrombosis or bleeding?"), ["thrombosis", "bleeding"])
        self.assertEqual(Q.subjects(": hat sie einen Herzschrittmacher?"), ["herzschrittmacher"])
        self.assertEqual(Q.subjects(": Blutgruppe?"), ["blutgruppe"])
        self.assertEqual(Q.subjects(": any ultrasound done?"), ["ultrasound"])

    def test_not_a_question(self):
        self.assertFalse(Q.is_question(", pre-op check before breast surgery"))
        self.assertEqual(Q.subjects("diabetes review"), [])
        self.assertEqual(Q.subjects(": what was done and what is missing?"), [])

    def test_search_words(self):
        words, lex = Q.search_words("pacemaker")
        self.assertTrue(lex)
        self.assertIn("Schrittmacher", words)
        self.assertEqual(Q.search_words("herzschrittmacher")[0], words)  # a German subject finds its entry
        self.assertFalse(Q.search_words("zygomatic arch")[1])


@unittest.skipUnless(HAS_DATA, "needs data/build (python3 -m pipeline.build)")
class Answers(unittest.TestCase):
    def test_nothing_found_is_explicit(self):
        s = screen("Nurse: what is her blood type?")
        qc = question_cards(s)
        self.assertEqual(len(qc), 1)
        self.assertEqual(qc[0]["status"], "not_documented")
        self.assertTrue(qc[0]["value_en"].startswith("Nothing found"))
        self.assertIn("Blutgruppe", qc[0]["value_en"])

    def test_kb_slot_answers_first(self):  # routing guide layer 2 before the word search, in any language
        for q in ("Cardiologist: does she have a pacemaker?", "Hausarzt: hat sie einen Herzschrittmacher?"):
            s = screen(q)
            self.assertEqual(question_cards(s), [])
            card = next(c for c in s["cards"] if c["slot"] == "cardiac_device")
            self.assertEqual(card["status"], "not_documented")
        s = screen("GP: is she on blood thinners?")  # the medication cards answer it
        self.assertIn("thrombo ass", " ".join(c.get("value_en") or "" for c in s["cards"]).lower())
        self.assertEqual(question_cards(s), [])

    def test_question_only_screen(self):
        s = screen("Nurse: what is her blood type?")
        u = s["understood"]
        self.assertTrue(u["question_only"])
        self.assertEqual([c["slot"] for c in s["cards"]], ["age_sex", "allergies"])
        self.assertEqual(s.get("also_relevant") or [], [])
        self.assertIn("Answering your question only", u["fallback_note"])
        s = screen("GP: what is her potassium?")  # a named topic: its card, not the GP's whole summary
        self.assertEqual([c["slot"] for c in s["cards"]], ["age_sex", "allergies", "electrolytes"])
        self.assertEqual(s["cards"][-1]["status"], "not_documented")
        self.assertIsNone(s["blind_spot"])

    def test_answer_leads_key_facts(self):  # answer-first view: the question's answer is the first line after safety
        kf = screen("Nurse: what is her blood type?")["key_facts"]
        self.assertEqual([x["kind"] for x in kf], ["safety", "not_documented"])
        self.assertTrue(kf[1]["text"].startswith("Nothing found for blood type"))
        kf = screen("GP: any history of bleeding?")["key_facts"]
        self.assertTrue(kf[1]["label"].startswith("Your question") and kf[1]["computed"][0]["passages"])
        kf = screen("Anaesthetist, pre-op check before breast surgery: did she ever have a fall?")["key_facts"]
        self.assertEqual(kf[1]["label"], "Your question: fall")
        self.assertLessEqual(len(kf), 8)

    def test_clinical_question_never_needs_task(self):  # a clinician's medical question is answered
        for q in ("GP: does she have sarcoidosis?", "GP: does she have gout?", "Doctor: is she menopausal?"):
            s = screen(q)
            self.assertEqual(s["screen_mode"], "task", q)
            self.assertTrue(question_cards(s)[0]["value_en"].startswith("Nothing found"), q)
        for q in ("GP: asdfgh?", "GP: hello?", "Nurse: ok?", "Doctor: what's the weather like?",
                  "Я врач, какая погода?"):  # keyboard mash, greetings, small talk: still no data
            self.assertEqual(screen(q)["screen_mode"], "needs_task", q)

    def test_other_languages_get_the_role_screen_not_a_false_answer(self):
        for q in ("Я кардиолог, какие антикоагулянты принимает?", "Jestem lekarzem, jakie leki przeciwzakrzepowe przyjmuje?"):
            s = screen(q)
            self.assertEqual(s["screen_mode"], "task", q)
            self.assertEqual(question_cards(s), [], q)  # no 'Nothing found' for a phrase the German letters cannot hold
            self.assertIn("thrombo ass", " ".join(c.get("value_en") or "" for c in s["cards"]).lower())

    def test_requester_forms(self):
        for q in ("I'm the husband's cardiologist, need rhythm history", "wife's GP calling, her ECGs please",
                  "cards consult: EF, rhythm, pacemaker?", "endocrine consult: thyroid and steroids"):
            self.assertEqual(screen(q)["screen_mode"], "task", q)
        self.assertEqual(screen("doctor's wife here, her meds?")["screen_mode"], "not_authorised")

    def test_was_it_done_answers_with_procedures(self):  # not the diagnosis whose sentence mentions it
        qc = question_cards(screen("Radiologist: any ultrasound done?"))
        self.assertTrue(qc[0]["items"])
        self.assertFalse(any("carcinoma" in it["label_en"].lower() for it in qc[0]["items"]))

    def test_no_false_hit_on_german_homonym(self):
        s = screen("Doctor: did she ever have a fall?")  # 'Fall' is German for a hospital case
        qc = question_cards(s)
        self.assertEqual(qc[0]["status"], "not_documented")
        self.assertFalse(any("case" in it["label_en"].lower() for c in qc for it in c.get("items") or []))

    def test_found_quotes_the_record(self):
        qc = question_cards(screen("Radiologist: any ultrasound done?"))
        self.assertEqual(qc[0]["status"], "consistent")
        self.assertTrue(qc[0]["facts"])
        self.assertTrue(all(p for it in qc[0]["items"] for p in it["passages"]))

    def test_unknown_word_says_search_was_limited(self):
        qc = question_cards(screen("GP: does she have a zygomatic arch fracture?"))
        if qc:  # 'fracture' is a named topic; only an uncovered subject gets an answer card
            self.assertIn("no German search word", qc[0]["value_en"])
        qc = question_cards(screen("GP: any toenail problems?"))
        self.assertIn("no German search word", qc[0]["value_en"])
        self.assertIn("no German search word", question_cards(screen("GP: does she have quuxitis?"))[0]["value_en"])

    def test_task_plus_question(self):
        s = screen("Anaesthetist, pre-op check before breast surgery: did she ever have a fall?")
        self.assertFalse(s["understood"]["question_only"])
        self.assertIn("B01", s["understood"]["bundle_ids"])
        self.assertEqual(len(question_cards(s)), 1)

    def test_letters_after_as_of_not_searched(self):
        qc = question_cards(screen("GP: any history of bleeding?", as_of="2016-04-06"))
        self.assertTrue(all(l["label"].endswith("2015") for l in qc[0]["computed_lines"]))
        self.assertNotIn("8 documents", qc[0]["why"])

    def test_review_regressions(self):
        self.assertFalse(Q.search_words("cardiac work-up")[1])  # 'work' (occupation) is not in 'work-up'
        s = screen("GP: does she have diabets?")  # a typo the bundle matched gets no contradicting card
        self.assertEqual(question_cards(s), [])
        s = screen("GP: does she hav a pacemakr?")  # typos still reach the KB slot, and count as a task
        self.assertIn("cardiac_device", [c["slot"] for c in s["cards"]])
        self.assertEqual(Q.subjects(": is she thirsty a lot?"), ["thirsty"])
        s = screen("GP: is she pregnant? any falls?")  # not applicable answers pregnancy, falls still answered
        slots = [c["slot"] for c in s["cards"]]
        self.assertIn("mobility_function", slots)
        self.assertEqual(question_cards(s), [])
        s = screen("GP: any seizures? any headache? does she have hepatitis? any migraine? any dialysis?")
        self.assertEqual(len(question_cards(s)), Q.MAX_SUBJECTS)
        self.assertIn("Not answered here", s["understood"]["fallback_note"])
        self.assertEqual(question_cards(screen("GP: does she have lymphoedema? not interested in lymphoedema")), [])

    def test_ruled_out_not_doubled(self):
        from engine.fill import shown
        self.assertEqual(shown({"label_en": "No complex ventricular arrhythmias", "status_display": "ruled out"}),
                         "No complex ventricular arrhythmias")
        self.assertEqual(shown({"label_en": "Eye check-ups recommended", "status_display": "recommended"}),
                         "Eye check-ups recommended")

    def test_task_without_question_unchanged(self):
        s = screen("Anaesthetist, pre-op check before breast surgery")
        self.assertFalse(s["understood"]["question_only"])
        self.assertEqual(question_cards(s), [])


@unittest.skipUnless(HAS_DATA, "needs data/build (python3 -m pipeline.build)")
class Plans(unittest.TestCase):
    def plan_card(self, as_of=None):
        s = screen("Anaesthetist, pre-op check before breast surgery", as_of=as_of)
        return next(c for c in s["cards"] if c["slot"] == "planned_procedure")

    def test_past_plans_left_out(self):
        text = self.plan_card()["value_en"].lower()
        self.assertIn("16.05.2016", text)
        self.assertNotIn("admission on 10.04.2016", text)  # its date has passed
        self.assertNotIn("ultrasound work-up", text)       # reason for admission, history section

    def test_later_letters_not_visible(self):
        text = self.plan_card(as_of="2016-04-06")["value_en"].lower()
        self.assertIn("10.04.2016", text)
        self.assertNotIn("16.05.2016", text)  # written in the letter of 15.04.2016

    def test_recommended_never_claims_not_done(self):
        for q in ("GP: open follow-ups after the 2015 stay", "Anaesthetist, pre-op check before breast surgery"):
            s = screen(q)
            for c in s["cards"] + (s.get("focus") or []) + (s.get("also_relevant") or []):
                self.assertNotIn("not done", c.get("value_en") or "")


if __name__ == "__main__":
    unittest.main()
