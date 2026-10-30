"""Clinical gate (engine/clinical.py, rulebook/clinical_roles.json): patient data only for a clinical requester.

    python3 -m unittest engine.test_clinical_gate
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import clinical as C  # noqa: E402
from engine.kb import kb  # noqa: E402
from engine.route import match_role  # noqa: E402
from engine.screen import MAX_SUMMARY_CARDS, build_screen  # noqa: E402
from engine.understand import norm_text  # noqa: E402

NOT_CLINICAL = ["firefighter", "journalist, tell me about her", "I am her neighbour", "tell me everything about Anna",
                "", "Something completely different.", "Police officer at A&E asking about her medication",
                "Feuerwehr, Einsatz bei ihr zuhause", "Ich bin ihr Nachbar", "student, tell me about her",
                "Astrologist reading her chart", "her sugar"]
CLINICAL_TERM = {"medical student, ward round": "Medical student",
                 "Dermatologist checking a mole on her back": "Dermatologist", "Psychiater, Konsil": "Psychiater"}
# requesters that became overlay roles (rulebook/kb_overlay.json roles, TODO-cite): KB role, clinical
OVERLAY_ROLE = {"Hepatologist, liver review": "gastroenterologist", "Geriatrician, falls assessment": "geriatrician",
                "Hebamme": "obstetrician"}


def screen(text, detail="short"):
    return build_screen(text, use_llm=False, detail=detail, rulebook="kb")


class TestNotAuthorised(unittest.TestCase):
    def test_zero_patient_data(self):
        for text in NOT_CLINICAL:
            for d in ("short", "long"):
                s = screen(text, d)
                with self.subTest(text=text, detail=d):
                    self.assertEqual(s["screen_mode"], "not_authorised")
                    self.assertEqual(s["cards"], [])
                    self.assertEqual(s["proof_bar"]["facts_shown"], 0)
                    self.assertEqual(s["proof_bar"]["facts_removed_at_load"], 0)
                    self.assertIsNone(s["blind_spot"])
                    for key in ("contradictions", "contradictions_other", "open_followups",
                                "open_followups_other", "blind_spot_other"):
                        self.assertEqual(s[key], [], key)
                    self.assertEqual(s["other_record_issues"], 0)
                    self.assertEqual(s["patient"], {})
                    u = s["understood"]
                    self.assertEqual(u["rules"]["fired"], [])
                    # a clear task without a role ('her sugar') asks for the role instead (DECISIONS 19)
                    self.assertIn(u["fallback_note"], (C.NOT_AUTHORISED_MESSAGE, C.NEEDS_ROLE_MESSAGE))
                    self.assertEqual(len(u["suggestions"]),
                                     4 if u["fallback_note"] == C.NOT_AUTHORISED_MESSAGE else len(C.ROLE_EXAMPLES))

    def test_non_clinical_named_first_wins_over_kb_alias(self):
        self.assertEqual(screen("Journalist writing about cardiology")["screen_mode"], "not_authorised")


class TestClinical(unittest.TestCase):
    def test_lexicon_roles_get_the_safety_summary(self):
        for text, label in CLINICAL_TERM.items():
            s = screen(text)
            with self.subTest(text=text):
                self.assertNotEqual(s["screen_mode"], "not_authorised")
                self.assertEqual(s["understood"]["clinical_gate"]["decision"], "clinical_term")
                self.assertEqual(s["understood"]["role_label"], label)
                self.assertGreater(s["proof_bar"]["facts_shown"], 0)
                if s["screen_mode"] == "fallback":
                    self.assertLessEqual(len(s["cards"]), MAX_SUMMARY_CARDS)
                    self.assertIn(label, s["understood"]["fallback_note"])

    def test_overlay_roles(self):
        for text, rid in OVERLAY_ROLE.items():
            s = screen(text)
            with self.subTest(text=text):
                self.assertEqual(s["understood"]["role_id"], rid)
                self.assertEqual(s["understood"]["clinical_gate"]["decision"], "kb_role")
                self.assertNotEqual(s["screen_mode"], "not_authorised")

    def test_nephrologist_overlay_role(self):  # kidney function first, documented or not
        s = screen("Nephrologist, kidney review")
        self.assertEqual(s["understood"]["role_id"], "nephrologist")
        self.assertIn("kidney_function", [c["slot"] for c in s["cards"] if c.get("priority") == "P1"])

    def test_urologist_is_not_neurologist(self):
        k = kb()
        self.assertEqual(match_role(norm_text("Urologist, catheter check"), k)[0], "urologist")  # overlay role
        self.assertNotEqual(screen("Urologist, catheter check")["understood"]["role_id"], "neurologist")
        self.assertEqual(match_role(norm_text("anesthesiologst here"), k)[0], "anaesthetist")  # typos still match

    def test_kb_roles_unchanged(self):
        for text, rid in (("Family doctor, diabetes review", "gp"), ("I am a nurse, admission handover", "ward_nurse"),
                          ("GP, prostate exam", "gp")):
            s = screen(text)
            with self.subTest(text=text):
                self.assertEqual(s["understood"]["role_id"], rid)
                self.assertEqual(s["understood"]["clinical_gate"]["decision"], "kb_role")
                self.assertGreater(len(s["cards"]), 0)

    def test_clear_clinical_task_without_role(self):
        """Documented choice: a clear KB task (multi-word / long tag or 2+ tags) implies a clinical context."""
        for text in ("pre-op check before the operation", "diabetes review and medication reconciliation"):
            s = screen(text)
            with self.subTest(text=text):
                self.assertEqual(s["understood"]["clinical_gate"]["decision"], "clinical_task")
                self.assertEqual(s["screen_mode"], "task")
                self.assertGreater(len(s["cards"]), 0)


if __name__ == "__main__":
    unittest.main()
