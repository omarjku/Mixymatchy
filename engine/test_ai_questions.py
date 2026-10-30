"""The optional LLM's reading of a question (engine/llm.py answer_slots / question_terms), with a fake client:

  a question in wording the rules do not know still reaches the KB card that answers it, and a topic no card
  covers is searched with the model's German words; the model never supplies facts, and junk ids / terms are
  dropped.

    python3 -m unittest engine.test_ai_questions
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import llm  # noqa: E402
from engine.screen import build_screen  # noqa: E402
from engine.test_llm import FakeClient, HAS_DATA, LLMTestBase  # noqa: E402


def answer(role, slots=(), terms=(), bundles=()):
    return {"request_kind": "clinical_task", "requester_role": role, "bundle_ids": list(bundles), "reason": "test",
            "focus_concepts": [], "answer_slots": list(slots), "question_terms": list(terms)}


class Validate(LLMTestBase):
    def test_only_real_slots_and_clean_terms_survive(self):
        out = llm.validate(answer("gp", ["kidney_function", "not_a_slot", "kidney_function"],
                                  [{"subject": "Fall", "terms_de": ["Sturz", "gestürzt", "x", "Sturz", "<script>"]},
                                   {"subject": "", "terms_de": ["Sturz"]},
                                   {"subject": "gait", "terms_de": []}]), self.kb)
        self.assertEqual(out["answer_slots"], ["kidney_function"])
        self.assertEqual(out["question_terms"], [{"subject": "fall", "terms_de": ["Sturz", "gestürzt"]}])

    def test_schema_asks_for_slots_and_terms(self):
        _sys, schema, *_ = llm.static_prompt(self.kb)
        self.assertIn("answer_slots", schema["required"])
        self.assertIn("question_terms", schema["required"])


@unittest.skipUnless(HAS_DATA, "needs data/build (python3 -m pipeline.build)")
class Screen(LLMTestBase):
    def screen(self, text, ans):
        llm.set_client(FakeClient(ans))
        return build_screen(text, use_llm=True, detail="short", rulebook="kb")

    def test_unknown_wording_reaches_the_slot(self):
        s = self.screen("GP: how are her kidneys doing these days?", answer("gp", ["kidney_function"]))
        self.assertIn("kidney_function", [c["slot"] for c in s["cards"]])

    def test_model_search_words_are_used_and_quoted(self):
        s = self.screen("GP: has she ever had a stumble at home?",
                        answer("gp", terms=[{"subject": "stumble", "terms_de": ["Sturz", "gestürzt"]}]))
        qc = [c for c in s.get("focus") or [] if c.get("group") == "question"]
        self.assertTrue(qc)
        self.assertIn("Sturz", qc[0]["searched"]["terms"])
        self.assertEqual(qc[0]["searched"]["ai_terms"], ["Sturz", "gestürzt"])
        if qc[0]["status"] == "not_documented":
            self.assertIn("suggested by the AI reading", qc[0]["value_en"])

    def test_model_cannot_open_a_refused_request(self):
        s = self.screen("hello", answer("gp", ["kidney_function"]))
        self.assertEqual(s.get("cards") or [], [])


if __name__ == "__main__":
    unittest.main()
