"""Answer lines (engine/answers.py, docs/DECISIONS.md 22) with a mocked LLM writer (no key, no network).

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


ATTACKS = [  # adversarial verifier (adv2): every one must be rejected
    ("number as word","n1",0,"Acetylsalicylic acid (Thrombo ASS) one hundred mg 1-0-0, as of April 2016."),
    ("number word invented","n1",0,"Acetylsalicylic acid (Thrombo ASS) 100 mg 1-0-0 for sixty days, as of April 2016."),
    ("number word LVEF","n1",1,"LVEF sixty percent, normal systolic LV function, 14 June 2015."),
    ("day swapped","n3",1,"HbA1c 6.4% (well-controlled type II diabetes), 6 January 2015."),
    ("day/month swap 13 June->6 Jan13","n3",1,"HbA1c 6.4% (well-controlled type II diabetes), 6 June 2013."),
    ("date swap weight","n3",2,"Weight 78 kg (4 April 2016), 67 kg (14 June 2015), 66 kg (15 April 2016); change -12 kg over 10 months."),
    ("unit mg->g","n1",0,"Acetylsalicylic acid (Thrombo ASS) 100 g 1-0-0, as of April 2016."),
    ("unit kg->g","n3",2,"Weight 78 g (14 June 2015), 67 g (4 April 2016), 66 g (15 April 2016); change -12 g over 10 months."),
    ("unit %->mmol","n3",1,"HbA1c 6.4 mmol/mol (well-controlled type II diabetes), 13 June 2015."),
    ("unit ug->mg","n3",0,"Metformin (Glucophage) 1000 mg 1-1-1, pioglitazone (Actos) 30 mg 0-1-0 and exenatide (Byetta) 5 mg s.c. 1-0-1, as of April 2016."),
    ("class added statin","n1",0,"Acetylsalicylic acid (Thrombo ASS) 100 mg 1-0-0 and a statin, as of April 2016."),
    ("class added anticoagulant","n1",0,"Acetylsalicylic acid (Thrombo ASS) 100 mg 1-0-0 plus an anticoagulant, as of April 2016."),
    ("class added beta blocker","n3",0,"Metformin (Glucophage) 1000 mg 1-1-1, pioglitazone (Actos) 30 mg 0-1-0 and exenatide (Byetta) 5 µg s.c. 1-0-1 and a beta-blocker, as of April 2016."),
    ("class added insulin","n3",0,"Metformin (Glucophage) 1000 mg 1-1-1, pioglitazone (Actos) 30 mg 0-1-0 and exenatide (Byetta) 5 µg s.c. 1-0-1, also insulin, as of April 2016."),
    ("negation: no allergy","n4",3,"Before contrast: head CT performed without contrast (native), no contrast media allergy, 14 June 2015; takes metformin (Glucophage) 1000 mg 1-1-1; kidney function (creatinine, eGFR) not documented."),
    ("negation: not on metformin","n4",3,"Before contrast: head CT performed without contrast (native) because of known contrast media allergy, 14 June 2015; does not take metformin (Glucophage) 1000 mg 1-1-1; kidney function (creatinine, eGFR) not documented."),
    ("negation: stopped aspirin","n1",0,"Acetylsalicylic acid (Thrombo ASS) 100 mg 1-0-0 was stopped, as of April 2016."),
    ("negation: no stenosis","n4",0,"June 2015: no carotid artery stenosis, left, 60%; dizziness and eye symptoms attributed to atherosclerotic carotid stenosis."),
    ("laterality flip left->right","n4",0,"June 2015: admission due to hypertensive crisis with dizziness and transient visual disturbance right eye; carotid artery stenosis, right, 60%."),
    ("laterality flip only","n4",0,"June 2015: admission diagnosis due to hypertensive crisis with dizziness and transient visual disturbance right eye (lasting several seconds); dizziness and eye symptoms attributed to atherosclerotic carotid stenosis; carotid artery stenosis, right, 60%."),
    ("value from another need (HbA1c in dx)","n3",3,"Diabetes mellitus type II with HbA1c 6.4%, 15 April 2016."),
    ("value from another need (weight in hba1c)","n3",1,"HbA1c 6.4% (well-controlled type II diabetes), 13 June 2015, weight 67 kg."),
    ("value from other need: LVEF 60 in aspirin","n1",0,"Acetylsalicylic acid (Thrombo ASS) 100 mg 1-0-0 as of April 2016, LVEF 60%."),
    ("wrong schedule","n1",0,"Acetylsalicylic acid (Thrombo ASS) 100 mg 0-0-1, as of April 2016."),
    ("wrong schedule words","n1",0,"Acetylsalicylic acid (Thrombo ASS) 100 mg twice daily, as of April 2016."),
    ("year changed","n3",1,"HbA1c 6.4% (well-controlled type II diabetes), 13 June 2016."),
    ("advice/interpretation","n1",0,"Acetylsalicylic acid (Thrombo ASS) 100 mg 1-0-0, as of April 2016; stop it before surgery."),
    ("percent changed 6.4->6,4 ok? 64","n3",1,"HbA1c 64% (well-controlled type II diabetes), 13 June 2015."),
    ("decimal shift","n3",1,"HbA1c 6.5% (well-controlled type II diabetes), 13 June 2015."),
]


GOOD = [  # paraphrases in the expected-answer style that must pass
    ("n1", 0, "Thrombo ASS (acetylsalicylic acid) 100 mg, once in the morning (1-0-0), as of April 2016."),
    ("n1", 1, "LVEF 60% with normal systolic LV function on 14 June 2015."),
    ("n3", 1, "HbA1c 6.4% on 13 June 2015; no later value documented."),
    ("n3", 2, "78 kg in June 2015, 67 kg on 4 April 2016 and 66 kg on 15 April 2016: about 12 kg lost over 10 months."),
    ("n4", 2, "Candesartan (Blopress) 16 mg twice daily (1-0-1), as of April 2016."),
    ("n5", 3, "Left carotid artery stenosis of 60% (June 2015); one letter (discharge letter 28.06.2015) says right."),
]


class Allowlist(unittest.TestCase):
    """verify() is an ALLOWLIST: tokens, units, value-date pairs, schedules and sides come from the line's facts."""

    @classmethod
    def setUpClass(cls):
        cls.st, cls.k = store(), kb()
        cls.n = {"n1": _needs(CASE1), "n3": _needs(CASE3), "n4": _needs(CASE4), "n5": _needs(CASE5)}

    def test_every_attack_is_rejected(self):
        for name, w, i, text in ATTACKS:
            ok, why = A.verify(self.st, self.k, self.n[w][i], text)
            self.assertFalse(ok, "%s passed: %s" % (name, text))

    def test_good_paraphrases_pass(self):
        for w, i, text in GOOD:
            ok, why = A.verify(self.st, self.k, self.n[w][i], text)
            self.assertTrue(ok, "%s rejected: %s" % (text, why))


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


class Questions(unittest.TestCase):
    """engine/ask.py question cards: the TOP picked need; 'Nothing found' stays as written."""

    def test_question_only_screen_is_header_plus_answer(self):
        s = build_screen("GP, did she ever have a fall?", use_llm=False)
        self.assertTrue(s["understood"]["question_only"])
        kinds = [ln["kind"] for ln in s["answer_lines"]]
        self.assertEqual(kinds, ["header", "not_documented"])
        self.assertTrue(s["answer_lines"][1]["text"].startswith("Nothing found for fall"))

    def test_question_slot_comes_first_on_a_task_screen(self):
        s = build_screen("Anaesthetist, pre-op check before quadrantectomy. Does she smoke?", use_llm=False)
        self.assertEqual(s["answer_lines"][1]["needs"], ["smoking_alcohol"])
        self.assertLessEqual(len(s["answer_lines"]) - 1, A.MAX_LINES)

    def test_found_question_is_written_and_verified_like_the_others(self):
        st, k = store(), kb()
        s = build_screen(CASE3, use_llm=False)
        it = next(c for c in s["cards"] if c.get("slot") == "hba1c")["items"][0]
        card = {"need": "ask_hba1c", "label_en": "Your question: HbA1c", "group": "question", "status": "consistent",
                "items": [it]}
        needs = A.pick_lines(st, k, s["cards"], s["understood"], s["contradictions"], CASE3, "2016-04-15", focus=[card])
        self.assertEqual(needs[0]["needs"], ["ask_hba1c"])
        when = A.fmt_date(it["date"])
        self.assertTrue(A.verify(st, k, needs[0], "HbA1c 6.4%% on %s." % when)[0])
        self.assertFalse(A.verify(st, k, needs[0], "HbA1c 7.1%% on %s." % when)[0])

    def test_nothing_found_never_goes_to_the_llm(self):
        st, k = store(), kb()
        s = build_screen("GP, did she ever have a fall?", use_llm=False)
        card = next(c for c in s["focus"] if c.get("group") == "question")
        needs = A.pick_lines(st, k, s["cards"], s["understood"], s["contradictions"], "", "2016-04-15", focus=[card])
        self.assertEqual(needs[0]["kind"], "nothing")
        lines, stats = A.finish(st, k, needs, A.Pending(None, 0.0, {"called": True, "cached": 0, "skipped": None,
                                                                    "cost_eur": 0.0, "ms": 0.0,
                                                                    "cached_text": {"L1": "Yes, she fell."}}))
        self.assertEqual(lines[0]["origin"], "template")
        self.assertEqual(lines[0]["text"], card["value_en"])


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
