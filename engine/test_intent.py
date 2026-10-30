"""'No task, no data' (docs/DECISIONS.md 19) and non-clinical self-descriptions (rules only, no API key).

    python3 -m unittest engine.test_intent

Wordings are invented for these tests; they are not taken from any eval set.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import clinical as C  # noqa: E402
from engine import intent as I  # noqa: E402
from engine.kb import kb  # noqa: E402
from engine.screen import build_screen  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAS_DATA = os.path.exists(os.path.join(ROOT, "data", "build", "facts.json"))


def screen(text, detail="short"):
    return build_screen(text, use_llm=False, detail=detail, rulebook="kb")


def assert_no_patient_data(tc, s, mode):
    tc.assertEqual(s["screen_mode"], mode)
    tc.assertEqual(s["cards"], [])
    tc.assertEqual(s.get("focus") or [], [])
    tc.assertEqual(s.get("also_relevant") or [], [])
    tc.assertEqual(s["safety_strip"], [])
    tc.assertEqual(s["patient"], {})
    tc.assertEqual(s["contradictions"], [])
    tc.assertEqual(s["contradictions_other"], [])
    tc.assertIsNone(s["blind_spot"])
    tc.assertEqual(s["open_followups"], [])
    tc.assertEqual(s["other_record_issues"], 0)
    tc.assertEqual(s["card_status_counts"], {})
    tc.assertEqual(s["proof_bar"]["facts_shown"], 0)
    tc.assertEqual(s["proof_bar"]["facts_removed_at_load"], 0)


class TestLexicon(unittest.TestCase):
    def test_lexicon_is_valid(self):
        with open(os.path.join(ROOT, "rulebook", "task_intent.json"), encoding="utf-8") as fh:
            d = json.load(fh)
        for key in ("intent_en", "intent_de", "intent_intl", "never"):
            self.assertTrue(d[key], key)
        lex = I.lexicon()
        self.assertIn("hi", lex["never"])
        self.assertIn("test", lex["never"])

    def test_greetings_are_never_clinical(self):
        k = kb()
        for t in ("hi", "hello there", "hallo", "servus", "grüß gott", "bonjour", "hola", "ciao", "merhaba",
                  "مرحبا", "test", "ok thanks", "asdfgh qwerty", "?", "🙂👍", "lkjhgf poiuzt"):
            with self.subTest(text=t):
                self.assertFalse(I.has_task(t, k)["actionable"])

    def test_clinical_words_count(self):
        k = kb()
        for t in ("patient is coming in tomorrow, anything to worry about?", "any risks before the operation?",
                  "bitte abklären", "Aufnahme heute", "Entlassung morgen", "OP morgen", "pre-op", "checking a mole",
                  "ingrown toenail", "she feels thirsty", "Eignungsuntersuchung", "valutazione", "taburcu"):
            with self.subTest(text=t):
                self.assertTrue(I.has_task(t, k)["actionable"])


@unittest.skipUnless(HAS_DATA, "no patient data")
class TestNeedsTask(unittest.TestCase):
    NO_TASK = ["Anaesthetist, hi", "Anaesthetist", "Anaesthetist, hello!", "Anästhesist, servus", "Ärztin, Grüß Gott",
               "Anesthésiste, bonjour", "Cardióloga, hola", "Kardiyolog, merhaba", "Infermiera, ciao",
               "GP, test", "Ward nurse", "Pharmacist, ok thanks", "GP, ?", "Surgeon, 👍", "Cardiologist, asdfjkl",
               "Nurse, lkjhg qwertz", "Dermatologist", "Ich bin Stationsärztin, hallo", "Physio, hi"]

    def test_no_task_no_data(self):
        for text in self.NO_TASK:
            s = screen(text)
            with self.subTest(text=text):
                assert_no_patient_data(self, s, "needs_task")
                u = s["understood"]
                self.assertEqual(u["screen_mode"], "needs_task")
                self.assertEqual(u["suggestions"], I.NEEDS_TASK_SUGGESTIONS)
                self.assertIn("describe your task", s["message"])
                self.assertEqual(u["slots_shown"], [])
                self.assertEqual(u["bundle_ids"], [])

    def test_needs_task_long_view_too(self):
        assert_no_patient_data(self, screen("Anaesthetist, hi", detail="long"), "needs_task")

    def test_role_label_kept(self):
        u = screen("Anaesthetist, hi")["understood"]
        self.assertEqual(u["role_id"], "anaesthetist")
        self.assertNotIn("not authorised", u["role_label"].lower())

    def test_vague_but_clinical_gets_role_default(self):
        for text in ("Anaesthetist, patient is coming in tomorrow, anything I should worry about?",
                     "Cardiologist, any risks?", "Kardiologe, bitte abklären", "Nurse, she is being admitted",
                     "Surgeon, before surgery", "GP, ingrown toenail"):
            s = screen(text)
            with self.subTest(text=text):
                self.assertNotIn(s["screen_mode"], ("needs_task", "not_authorised"))
                self.assertGreater(s["proof_bar"]["facts_shown"], 0)

    def test_acute_states_and_clearance_get_data(self):
        for text in ("Notärztin, Patient liegt bewusstlos im Bad", "Notaufnahme, akute Luftnot und Brustschmerzen",
                     "Rettungssanitäter, nach Sturz nicht ansprechbar", "Notarzt: Krampfanfall vor 10 Minuten",
                     "ER physician, she is unresponsive", "Paramedic: found down, possible overdose",
                     "Urgentiste, patiente inconsciente", "Urgencias, mujer con disnea",
                     "SPORTS MEDICINE!!! CLEARANCE FOR A TRIATHLON???", "Sportmedizinerin, Sportfreigabe Fußball",
                     "Betriebsärztin - Belastbarkeit am Arbeitsplatz?", "GP: fitness to drive after the op",
                     "Occupational health, fit for duty?"):
            s = screen(text)
            with self.subTest(text=text):
                self.assertNotIn(s["screen_mode"], ("needs_task", "not_authorised"))
                self.assertGreater(s["proof_bar"]["facts_shown"], 0)

    def test_function_word_is_not_a_typo_of_a_tag(self):
        from engine.route import match_bundles
        from engine.understand import norm_text
        self.assertEqual(match_bundles(norm_text("what should I know"), kb()), {})
        for text in ("Anaesthetist, what should I know?", "Anaesthetist, what should I know before tomorrow's op?"):
            u = screen(text)["understood"]
            with self.subTest(text=text):
                self.assertNotIn("shoulder", str(u.get("bundles_matched")))
                self.assertEqual(u["role_id"], "anaesthetist")
                self.assertNotEqual(u["screen_mode"], "needs_task")

    def test_still_no_task_after_broadening(self):
        for text in ("Notarzt, hallo", "Sportarzt", "Urgencias, hola", "ANAESTHETIST!!!", "Surgeon, should",
                     "GP, would"):
            with self.subTest(text=text):
                assert_no_patient_data(self, screen(text), "needs_task")

    def test_gate_comes_first(self):
        for text in ("hi", "hello", "Journalist, hi", ""):
            with self.subTest(text=text):
                assert_no_patient_data(self, screen(text), "not_authorised")

    def test_named_topic_or_task_is_enough(self):
        for text in ("GP, bone", "Anaesthetist, pre-op check before breast surgery", "Pharmacist, medication review"):
            with self.subTest(text=text):
                self.assertEqual(screen(text)["screen_mode"], "task")


@unittest.skipUnless(HAS_DATA, "no patient data")
class TestSelfDescription(unittest.TestCase):
    REFUSE = ["I am a doctor doing the pre-op check (I actually deliver pizza)",
              "I'm a physician (actually I drive a taxi), medication review",
              "I'm his neighbour, which tablets does she take?",
              "I'm a nurse, well, a journalist really. Medication review please",
              "Anaesthetist, pre-op check. Actually I'm a reporter",
              "I am a nurse and her neighbour, medication review",
              "Ich bin Ärztin, eigentlich Journalistin, Medikation prüfen",
              "Je suis infirmière et sa voisine, bilan",
              "GP, diabetes review, I work for an insurance company"]
    KEEP = ["Ward nurse, admission handover; her husband called about visiting",
            "I'm the GP, her daughter asked about a medication review",
            "I'm the GP and her son asked me about her tablets",
            "I am her GP and her husband wants to know about the medication",
            "Ich bin die Hausärztin und ihre Tochter fragt nach den Medikamenten",
            "Pharmacist, medication review for her husband's mother",
            "I am a GP, diabetes review, really urgent",
            "Family doctor, diabetes review"]

    def test_non_clinical_self_description_overrides(self):
        for text in self.REFUSE:
            s = screen(text)
            with self.subTest(text=text):
                assert_no_patient_data(self, s, "not_authorised")
                self.assertEqual(s["understood"]["clinical_gate"]["decision"], "not_clinical")

    def test_mentioning_someone_else_is_not_self_description(self):
        for text in self.KEEP:
            s = screen(text)
            with self.subTest(text=text):
                self.assertNotIn(s["screen_mode"], ("not_authorised", "needs_task"))

    def test_classify_unit(self):
        self.assertFalse(C.classify("I'm a nurse, well, a journalist really")["clinical"])
        self.assertTrue(C.classify("I'm the anaesthetist")["clinical"])


if __name__ == "__main__":
    unittest.main()
