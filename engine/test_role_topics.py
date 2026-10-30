"""Role-typical topics and role routing for new situations (rules only, no API key):

  a role that borrows a KB bundle (overlay roles, or a KB role whose task was not recognised) also gets the
  topics its own mindset / often_missing text names (rulebook/kb_overlay.json role_topics), each found or
  'not documented'; a role on its own bundle gets none; a judgement question keeps the role's view; named
  topics inside the role's own task keep its bundle.

    python3 -m unittest engine.test_role_topics

Wordings here are invented for these tests; they are not taken from any eval set.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.screen import _asks_judgement, build_screen  # noqa: E402

HAS_DATA = os.path.exists(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       "data", "build", "facts.json"))


def screen(text):
    return build_screen(text, use_llm=False, detail="short", rulebook="kb")


def needs(s):
    return {c.get("need"): c for c in (s.get("cards") or []) + (s.get("focus") or [])}


class Judgement(unittest.TestCase):
    def test_words(self):
        self.assertTrue(_asks_judgement("is she fit to fly next month?"))
        self.assertTrue(_asks_judgement("Sportfreigabe ja oder nein?"))
        self.assertFalse(_asks_judgement("what is her blood type?"))
        self.assertFalse(_asks_judgement("is she on blood thinners?"))


@unittest.skipUnless(HAS_DATA, "needs data/build (python3 -m pipeline.build)")
class RoleTopics(unittest.TestCase):
    def test_borrowed_bundle_gets_role_topics(self):
        s = screen("Travel clinic doctor, consultation before a long trip abroad")
        self.assertIn("vaccination", s["understood"]["role_topics"])
        card = needs(s)["topic_vaccination"]
        self.assertEqual(card["status"], "not_documented")
        self.assertIn("usually needs", card["why"])
        self.assertEqual(card["origins"], ["role topic"])

    def test_own_bundle_gets_none(self):
        s = screen("Cardiologist, blood pressure review")
        self.assertEqual(s["understood"]["role_topics"], [])

    def test_judgement_keeps_role_view(self):
        s = screen("Cardiologist: is she fit for a marathon, yes or no?")
        u = s["understood"]
        self.assertFalse(u["question_only"])
        self.assertNotIn("Your question", " ".join(u.get("task_labels") or []))
        self.assertIn("lvef", [c.get("slot") for c in s["cards"]])
        self.assertFalse([c for c in s.get("focus") or [] if c.get("group") == "question"])

    def test_named_topic_in_own_domain_keeps_bundle(self):
        s = screen("Oncologist, I need the receptor status")
        self.assertIn("B11", s["understood"]["bundle_ids"])


if __name__ == "__main__":
    unittest.main()
