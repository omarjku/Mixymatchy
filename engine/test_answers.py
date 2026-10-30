"""Answer lines (engine/answers.py, docs/DECISIONS.md 21) with a mocked LLM writer (no key, no network).

    python3 -m unittest engine.test_answers
"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "backend"))

from engine import answers as A  # noqa: E402
from engine import llm, llm_budget  # noqa: E402
from engine.data import store  # noqa: E402
from engine.kb import kb  # noqa: E402
from engine.screen import build_screen  # noqa: E402
from engine.test_keyfacts import CASE1, CASE2, CASE3, CASE4, CASE5  # noqa: E402
from engine.test_llm import FakeClient, LLMTestBase  # noqa: E402

CASES = (CASE1, CASE2, CASE3, CASE4, CASE5)


def _needs(text):
    s = build_screen(text, use_llm=False)
    return A.pick_lines(store(), kb(), s["cards"], s["understood"], s["contradictions"], text, "2016-04-15")


def writer(texts):
    """Fake model: answers each line id of the batch with texts[need ids] (or the first need id)."""
    def answer(kw):
        batch = json.loads(kw["messages"][0]["content"].split("\n", 1)[1])
        return {"lines": [{"id": x["id"], "text": texts.get(x["need"], texts.get("*", ""))} for x in batch]}
    return answer


class Picking(unittest.TestCase):
    """The rules pick: 3-4 needs in KB order, the composite as one line, nothing repeated."""

    @classmethod
    def setUpClass(cls):
        cls.n = {i: _needs(t) for i, t in enumerate(CASES, 1)}

    def test_at_most_four_lines(self):
        for i, needs in self.n.items():
            self.assertTrue(3 <= len(needs) <= A.MAX_LINES, i)

    def test_kb_order_and_merges(self):
        self.assertEqual([n["needs"] for n in self.n[3]], [["med_antidiabetic"], ["hba1c"], ["weight"], ["diabetes_dx"]])
        self.assertEqual(self.n[2][0]["needs"], ["cancer_histology", "tnm_grade"])  # same group and shape: merged
        self.assertEqual(self.n[2][-1]["needs"], ["board_recommendation", "planned_procedure"])

    def test_composite_keeps_its_not_documented_slot(self):
        comp = next(n for n in self.n[4] if n["kind"] == "composite")
        self.assertIn("kidney_function", comp["needs"])
        self.assertTrue(comp["missing"])
        txt = A.template(store(), kb(), comp)
        self.assertIn("metformin", txt)
        self.assertIn("without contrast", txt)
        self.assertIn("not documented", txt)

    def test_same_episode_and_shown_values_not_repeated(self):
        ids = [x for n in self.n[4] for x in n["needs"]]
        self.assertNotIn("stroke_tia_hx", ids)   # same June 2015 episode as the event line
        self.assertNotIn("carotid_stenosis", ids)  # its 'left, 60%' is the event line's cause
        self.assertIn("60%", A.template(store(), kb(), self.n[4][0]))

    def test_laterality_carries_the_minority_side(self):
        car = next(n for n in self.n[5] if n["needs"] == ["carotid_stenosis"])
        self.assertIn("says right", A.template(store(), kb(), car))

    def test_gated_screen_has_no_answer_lines(self):
        self.assertEqual(build_screen("hi", use_llm=False).get("answer_lines") or [], [])


class Verify(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st, cls.k = store(), kb()
        cls.n1, cls.n3 = _needs(CASE1), _needs(CASE3)

    def ok(self, n, text):
        return A.verify(self.st, self.k, n, text)[0]

    def test_good_sentence_passes(self):
        self.assertTrue(self.ok(self.n1[0], "Thrombo ASS (acetylsalicylic acid) 100 mg, once in the morning (1-0-0), "
                                            "as of April 2016."))
        self.assertTrue(self.ok(self.n3[2], "78 kg in June 2015, 67 kg on 4 April 2016 and 66 kg on 15 April 2016: "
                                            "about 12 kg lost over 10 months."))

    def test_invented_number_rejected(self):
        self.assertFalse(self.ok(self.n1[0], "Thrombo ASS (acetylsalicylic acid) 150 mg 1-0-0."))
        self.assertFalse(self.ok(self.n3[1], "HbA1c 6.4% in March 2015."))  # month not in the facts

    def test_extra_drug_or_diagnosis_rejected(self):
        self.assertFalse(self.ok(self.n1[0], "Thrombo ASS (acetylsalicylic acid) 100 mg 1-0-0 and clopidogrel."))
        self.assertFalse(self.ok(self.n1[1], "LVEF 60% on 14 June 2015, suggesting heart failure."))

    def test_dropped_fact_and_false_not_documented_rejected(self):
        self.assertFalse(self.ok(self.n3[0], "Metformin (Glucophage) 1000 mg 1-1-1 and pioglitazone (Actos) 30 mg 0-1-0."))
        self.assertFalse(self.ok(self.n1[1], "LVEF 60% on 14 June 2015; kidney function not documented."))
        self.assertFalse(self.ok(self.n1[3], "Haemoglobin and coagulation are normal."))  # must say not documented


class Writer(LLMTestBase):
    GOOD = {"Antiplatelets and anticoagulants": "Thrombo ASS (acetylsalicylic acid) 100 mg once in the morning "
                                                "(1-0-0), as of April 2016.",
            "*": "Made-up 999 mg."}

    def setUp(self):
        super().setUp()
        self.st, self.k, self.needs = store(), kb(), _needs(CASE1)

    def run_writer(self, use_llm=True):
        return A.finish(self.st, self.k, self.needs, A.start(self.st, self.k, self.needs, use_llm))

    def test_good_sentence_used_bad_ones_fall_back(self):
        fake = self.client(writer(self.GOOD))
        lines, stats = self.run_writer()
        self.assertEqual(len(fake.calls), 1)  # one batched call for all lines
        params = fake.calls[0]
        self.assertEqual(params["system"][0]["cache_control"], {"type": "ephemeral"})
        self.assertLessEqual(params["max_tokens"], 600)
        self.assertEqual((lines[0]["origin"], lines[0]["verified"]), ("llm", True))
        self.assertIn("once in the morning", lines[0]["text"])
        self.assertTrue(all(ln["origin"] == "template" for ln in lines[1:]))
        self.assertEqual((stats["llm"], stats["template"], stats["rejected"]), (1, 3, 3))
        self.assertTrue(lines[0]["passages"])  # Source stays

    def test_extra_drug_rejected(self):
        self.client(writer({"*": "Thrombo ASS (acetylsalicylic acid) 100 mg 1-0-0, plus clopidogrel 75 mg."}))
        lines, stats = self.run_writer()
        self.assertEqual(lines[0]["origin"], "template")
        self.assertEqual(stats["rejected"], 4)

    def test_cache_by_need_and_facts(self):
        fake = self.client(writer(self.GOOD))
        self.run_writer()
        lines, stats = self.run_writer()
        self.assertEqual(len(fake.calls), 2)  # the rejected lines are asked again ...
        self.assertEqual(stats["cached"], 1)  # ... the verified one comes from the cache
        self.assertEqual(lines[0]["origin"], "llm")
        self.assertEqual(len(json.loads(fake.calls[1]["messages"][0]["content"].split("\n", 1)[1])), 3)

    def test_timeout_falls_back_to_templates(self):
        os.environ["SECOND_LOOK_LLM_TIMEOUT"] = "0.2"
        self.client(writer(self.GOOD), delay=1.0)
        lines, stats = self.run_writer()
        self.assertEqual(stats["skipped"], "timeout")
        self.assertTrue(all(ln["origin"] == "template" for ln in lines))
        self.assertLess(stats["ms"], 900)

    def test_no_key_falls_back_to_templates(self):
        saved = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            llm.set_client(None)
            lines, stats = self.run_writer()
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved
        self.assertFalse(stats["called"])
        self.assertEqual(stats["skipped"], "no key")
        self.assertTrue(all(ln["origin"] == "template" for ln in lines))
        self.assertEqual([ln["text"] for ln in lines], [A.template(self.st, self.k, n) for n in self.needs])

    def test_budget_stop_falls_back_to_templates(self):
        os.environ["SECOND_LOOK_LLM_MAX_CALLS_PER_DAY"] = "0"
        fake = self.client(writer(self.GOOD))
        lines, stats = self.run_writer()
        self.assertEqual(len(fake.calls), 0)
        self.assertTrue(all(ln["origin"] == "template" for ln in lines))
        self.assertIn(stats["skipped"], ("daily_cap", "budget"))

    def test_screen_records_stats(self):
        def answer(kw):  # the gate reading and the writer share the fake client
            if "lines" in json.dumps(kw["output_config"]["format"]["schema"]["properties"]):
                return writer(self.GOOD)(kw)
            return {"request_kind": "clinical_task", "requester_role": "anaesthetist", "bundle_ids": ["B01"],
                    "reason": "pre-op check", "focus_concepts": []}
        self.client(answer)
        s = build_screen(CASE1, use_llm=True)
        st = s["understood"]["answer_lines_llm"]
        self.assertTrue(st["called"])
        self.assertEqual(st["llm"], 1)
        self.assertEqual(s["answer_lines"][0]["kind"], "header")
        self.assertEqual(s["answer_lines"][1]["origin"], "llm")
        llm_budget.reset()


if __name__ == "__main__":
    unittest.main()
