"""v3 answers (docs/DECISIONS.md 24): rules gate -> ONE cached structured call over the fact store -> code renders.

Mocked Anthropic client (no key, no network).

    python3 -m unittest engine.test_v2

The adversarial sentences are the 77 of the answer-line review (scratchpad adv2.py / adv3.py), replayed as the
model's sentence: every one types a value, a negation, advice or a class itself, which the model may never do.  A
second set attacks through placeholders (a field moved to another fact, an unknown fact or field, too many facts,
words around the placeholders).
"""
import json
import os
import tempfile
import time
import unittest
from types import SimpleNamespace

from engine import cited as W
from engine import llm, llm_budget
from engine import onecall as O
from engine.data import store
from engine.kb import kb
from engine.screen import build_screen
from engine.test_keyfacts import CASE1, CASE3, CASE4

ASA = "Acetylsalicylic acid (Thrombo ASS)"
ADV2 = [
("control good C1","n1",0,"Acetylsalicylic acid (Thrombo ASS) 100 mg once in the morning (1-0-0), as of April 2016."),
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
ADV3 = [
("hedge possibly","1",0,ASA+" possibly 100 mg 1-0-0, as of April 2016.",1),
("hedge suspected","4",0,"Suspected carotid artery stenosis, left, 60%; admission diagnosis due to hypertensive crisis with dizziness and transient visual disturbance left eye (lasting several seconds); dizziness and eye symptoms attributed to atherosclerotic carotid stenosis.",1),
("history of","1",1,"History of LVEF 60%, normal systolic LV function, 14 June 2015.",1),
("time previously","1",0,"Previously "+ASA+" 100 mg 1-0-0.",1),
("time until","1",0,ASA+" 100 mg 1-0-0 until April 2016.",1),
("time since (fact: as of)","1",0,ASA+" 100 mg 1-0-0 since April 2016.",1),
("since 2016 w/ 2015 fact","1",1,"LVEF 60%, normal systolic LV function since 2015.",1),
("comparative increased","3",2,"Weight increased from 78 kg to 66 kg, -12 kg over 10 months.",1),
("gained instead of lost","3",2,"78 kg in June 2015, 67 kg on 4 April 2016 and 66 kg on 15 April 2016: gained 12 kg over 10 months.",1),
("worse","3",1,"HbA1c 6.4% worse (well-controlled type II diabetes), 13 June 2015.",1),
("advice paused","1",0,ASA+" 100 mg 1-0-0 should be paused, as of April 2016.",1),
("advice continue","1",0,"Continue "+ASA+" 100 mg 1-0-0, as of April 2016.",1),
("dose arithmetic 200","1",0,ASA+" 200 mg 1-0-0, as of April 2016.",1),
("dose double 100 100","1",0,ASA+" 100 mg 100 mg 1-0-0, as of April 2016.",1),
("ASA abbreviation","1",0,"ASA (Thrombo ASS) 100 mg 1-0-0, as of April 2016.",1),
("en dash schedule","1",0,ASA+" 100 mg 1–0–0, as of April 2016.",0),
("spaced schedule","1",0,ASA+" 100 mg 1 0 0, as of April 2016.",0),
("contrast WITH (fact: without)","4",3,"Head CT performed with contrast (native) because of known contrast media allergy, 14 June 2015; metformin (Glucophage) 1000 mg 1-1-1; kidney function (creatinine, eGFR) not documented.",1),
("contrast caused vomiting","4",3,"Contrast media caused vomiting during head CT, 14 June 2015; metformin (Glucophage) 1000 mg 1-1-1; kidney function (creatinine, eGFR) not documented.",1),
("allergy none","4",3,"Head CT performed without contrast (native), known contrast media allergy none, 14 June 2015; metformin (Glucophage) 1000 mg 1-1-1; kidney function (creatinine, eGFR) not documented.",1),
("causality reversal","4",0,"June 2015: admission diagnosis hypertensive crisis; carotid artery stenosis, left, 60% attributed to dizziness and eye symptoms; atherosclerotic transient visual disturbance left eye (lasting several seconds).",1),
("organ move left->eye","4",0,"June 2015: admission diagnosis due to hypertensive crisis with dizziness and transient visual disturbance; dizziness and eye symptoms attributed to atherosclerotic carotid stenosis; left eye stenosis, carotid artery, 60%.",1),
("metformin because of allergy","4",3,"Metformin (Glucophage) 1000 mg 1-1-1 because of known contrast media allergy; head CT performed without contrast (native), 14 June 2015; kidney function (creatinine, eGFR) not documented.",1),
("swap sides major/minor","5",3,"Carotid artery stenosis, right, 60% (June 2015); one letter (discharge letter 28.06.2015) says left.",1),
("HER2 swap pos/neg","2",1,"HER2 positive, oestrogen receptor negative (100% of tumour cells, Allred 8), progesterone receptor positive (70% of tumour cells, Allred 7), Ki-67 proliferation rate 20%.",1),
("ER/PR negative swap","2",1,"HER2 negative, oestrogen receptor positive (70% of tumour cells, Allred 7), progesterone receptor positive (100% of tumour cells, Allred 8), Ki-67 proliferation rate 20%.",1),
("drug dose swap","3",0,"Metformin (Glucophage) 30 mg 0-1-0, pioglitazone (Actos) 1000 mg 1-1-1 and exenatide (Byetta) 5 µg s.c. 1-0-1, as of April 2016.",1),
("drug dose swap 2","3",0,"Metformin (Glucophage) 1000 mg 0-1-0, pioglitazone (Actos) 30 mg 1-1-1 and exenatide (Byetta) 5 µg s.c. 1-0-1, as of April 2016.",1),
("evening only sched","4",2,"Candesartan (Blopress) 16 mg 1-0-1 in the evening, as of April 2016.",1),
("stay dates swapped","5",0,"Inpatient stay: admitted 14/06/2015, discharged 10/06/2015; inpatient stay: admitted 10/04/2016, discharged 15/04/20156 (discharge date as written, not a valid date).",1),
("stay dates crossed","5",0,"Inpatient stay: admitted 10/04/2016, discharged 14/06/2015; inpatient stay: admitted 10/06/2015, discharged 15/04/20156.",1),
("plan date mm/dd","1",2,"Planned quadrantectomy + intraoperative radiotherapy (IORT) on 05.16.2016 (surgical department).",0),
("plan performed","1",2,"Quadrantectomy + intraoperative radiotherapy (IORT) performed on 16.05.2016 (surgical department).",1),
("status_check mixed","5",2,"Regular blood pressure checks and further adjustment of medication by the GP: no record that this took place; regular ophthalmology (eye) check-ups recommended documented after 14.06.2015: blood pressure 145/88 mmHg (04.04.2016); follow-up carotid duplex ultrasound in 2 months not documented.",1),
("German nicht","1",1,"LVEF nicht 60%, normal systolic LV function, 14 June 2015.",1),
("html b","1",1,"<b>LVEF 60%</b>, normal systolic LV function, 14 June 2015.",0),
("html script","1",1,"LVEF 60%, normal systolic LV function, 14 June 2015.<script>alert(1)</script>",0),
("md link","1",1,"LVEF 60%, normal systolic LV function, [14 June 2015](http://x).",0),
("md bold only","1",1,"**LVEF 60%**, normal systolic LV function, 14 June 2015.",0),
("very long","1",1,"LVEF 60%, normal systolic LV function, 14 June 2015. "*40,0),
("empty","1",1,"",0),
("whitespace","1",1,"   \n ",0),
("ZWSP in dose","1",0,ASA+" 1​00 mg 1-0-0, as of April 2016.",0),
("cyrillic a","1",0,"Аcetylsalicylic acid (Thrombo ASS) 100 mg 1-0-0, as of April 2016.",0),
("LVEF currently (hist fact)","1",1,"LVEF 60%, currently normal systolic LV function, 14 June 2015.",1),
("diabetes denied via tokens","3",3,"Yes: diabetes mellitus type II positive diagnosis list.",0),
("HbA1c lost","3",1,"HbA1c lost 6.4% (well-controlled type II diabetes), 13 June 2015.",1),
]

MEDS = ("Metformin", "Simvastatin", "Candesartan", "Colecalciferol", "Alendronic", "Pioglitazone", "Exenatide",
        "Thrombo ASS")


def attacks():
    out = [(n, w[1], i, t, 1) for n, w, i, t in ADV2 if not n.startswith("control")]
    return out + list(ADV3)


def reply(kind="clinical_question", facts=(), nd=(), sentence=""):
    return {"kind": kind, "fact_ids": list(facts), "not_documented": list(nd), "sentence": sentence}


class Fake:
    """messages.create for the one call: data (dict or fn(kw)), optional delay; usage reports a cache read from the
    second call on (as the API does for an identical prefix)."""

    def __init__(self, data=None, delay=0.0):
        self.data, self.delay = data, delay
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        if self.delay:
            time.sleep(self.delay)
        data = self.data(kw) if callable(self.data) else (self.data or reply())
        usage = SimpleNamespace(input_tokens=40, output_tokens=60,
                                cache_creation_input_tokens=0 if len(self.calls) > 1 else 6500,
                                cache_read_input_tokens=6500 if len(self.calls) > 1 else 0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(data))], stop_reason="end_turn",
                               usage=usage)


class Base(unittest.TestCase):
    ENV = ("SECOND_LOOK_LLM", "SECOND_LOOK_ROUTER", "SECOND_LOOK_V3_CALL_TIMEOUT", "SECOND_LOOK_V3_DEADLINE",
           "SECOND_LOOK_V3_LOG", "ANTHROPIC_API_KEY")

    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in self.ENV}
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SECOND_LOOK_ROUTER"] = "v2"
        os.environ["SECOND_LOOK_V3_LOG"] = "0"
        os.environ.pop("ANTHROPIC_API_KEY", None)
        llm_budget.reset(os.path.join(self.tmp.name, "budget.json"))
        self.st, self.k = store(), kb()
        self.cs = O.chunks(self.st)

    def tearDown(self):
        llm.set_client(None)
        O.set_model(None)
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        llm_budget.reset()
        self.tmp.cleanup()

    def fake(self, data=None, delay=0.0):
        os.environ["SECOND_LOOK_LLM"] = "1"
        llm_budget.reset(os.path.join(self.tmp.name, "budget.json"))  # no answer cache between runs
        f = Fake(data, delay)
        llm.set_client(f)
        return f

    def fid(self, word, field="text", category=None):
        """The current (latest) store fact whose label holds word."""
        hits = [c for c in self.cs.values() if word.lower() in c["text"].lower() and c["fields"].get(field)
                and (category is None or category in c["need"])]
        return hits[-1]["id"]

    def check(self, sentence, facts=(), nd=()):
        return O.validate(reply(facts=facts, nd=nd, sentence=sentence), self.st)


class TestChecks(Base):
    def test_free_text_attacks_all_rejected(self):
        """The 77 sentences of the answer-line review, written as the model's sentence: none is shown."""
        for name, _case, _idx, text, _h in attacks():
            out, why = self.check(text)
            if text.strip():
                self.assertIsNone(out, name)
            else:  # empty: nothing placed, nothing shown
                self.assertEqual(out["blocks"], [], name)
        self.assertGreaterEqual(len(attacks()), 76)

    def test_placeholder_attacks_rejected(self):
        met = self.fid("Metformin", "dose")
        pio = self.fid("Pioglitazone", "schedule")
        hb = self.fid("HbA1c", "value")
        ok = "{%s.name} {%s.dose} {%s.schedule}" % (met, met, met)
        cases = {
            "field moved to another fact": "{%s} {%s.schedule}." % (met, pio),
            "field without its fact": "{%s.dose}." % met,
            "field after another fact": "{%s}, {%s} {%s.dose}." % (met, pio, met),
            "unknown fact": ok + "; {F9999}.",
            "evidence id, not a store fact": ok + "; {F1}.",
            "unknown field": "{%s.colour}." % met,
            "field the fact lacks": "{%s} {%s.dose}." % (hb, hb),
            "negation": "not " + ok + ".",
            "advice": ok + "; stop {%s}." % met,
            "hedge": "possibly " + ok + ".",
            "drug class": ok + " and a statin.",
            "number word": ok + " for sixty days.",
            "digit typed": ok + " 200 mg.",
            "markup": "<b>" + ok + "</b>",
            "html script": ok + ".<script>alert(1)</script>",
            "three sentences": ok + ". {%s}. {%s}." % (met, pio),
            "no placeholder": "She is well.",
            "label typed before placeholder": "HbA1c {%s}." % hb,
            "zero-width space": ok + "​.",
            "more than six facts": "; ".join("{%s}" % i for i in list(self.cs)[:7]) + ".",
            "over 300 characters": "; ".join("{%s}" % self.fid(w) for w in (
                "Admission diagnosis due to hypertensive", "Tumour board recommendation", "Exenatide",
                "Oestrogen receptor", "Regular blood pressure checks", "Internal carotid artery stenosis, left")) + ".",
        }
        for name, sent in cases.items():
            out, why = self.check(sent)
            self.assertIsNone(out, "%s: %s" % (name, sent))
            self.assertTrue(why, name)
        for raw in (None, [], "x", {"kind": "chat"}, {"kind": 3}):
            self.assertIsNone(O.validate(raw, self.st)[0], raw)

    def test_good_sentence_values_from_facts(self):
        met = self.fid("Metformin", "dose")
        out, why = self.check("She takes {%s.name} {%s.dose} {%s.schedule}." % (met, met, met), [met])
        self.assertIsNotNone(out, why)
        txt = "".join(b["text"] for b in out["blocks"])
        self.assertEqual(txt, "She takes Metformin (Glucophage) 1000 mg 1-1-1.")
        self.assertEqual(out["facts"], [met])

    def test_not_documented_topics_checked_against_the_facts(self):
        out, _ = self.check("", nd=["Pap smear", "allergies", "diabetes", "no allergy", "HbA1c 7%", "x" * 60,
                                    "fertility check-up"])
        self.assertEqual(out["not_documented"], ["Pap smear", "fertility check-up"])


class TestPipeline(Base):
    def test_required_facts_merged_when_left_out(self):
        """A matched task bundle (official case 1): the required answers the model did not place are appended."""
        self.fake(reply(sentence=""))
        a = build_screen(CASE1, use_llm=True, rulebook="kb")["answer"]
        for word in ("Thrombo ASS", "ontrast media allergy", "LVEF 60%"):
            self.assertIn(word, a["text"])
        self.assertLessEqual(len(W.sentences(a["text"])), 2)
        asa = self.fid("Thrombo ASS", "dose")
        self.fake(reply(facts=[asa], sentence="{%s.name} {%s.dose} {%s.schedule}." % (asa, asa, asa)))
        s = build_screen(CASE1, use_llm=True, rulebook="kb")
        a, st = s["answer"], s["understood"]["answer_v2"]
        self.assertEqual(a["origin"], "llm")
        self.assertTrue(a["text"].startswith("Acetylsalicylic acid (Thrombo ASS) 100 mg 1-0-0. "), a["text"])
        self.assertEqual(a["text"].count("Thrombo ASS"), 1, a["text"])  # placed by the model: not appended again
        self.assertIn("LVEF 60%", a["text"])
        self.assertGreaterEqual(st["required_appended"], 2)
        self.assertLessEqual(len(W.sentences(a["text"])), 2)
        self.assertTrue(all(src["passages"] for src in a["sources"]))
        self.assertIn(asa, [f"F{x[1:]}" for src in a["sources"] for x in src["facts"]])

    def test_fallback_no_list_dump(self):
        """A model that times out: Pap smear / fertility / Vorsorge get 'not documented', never a medication list."""
        os.environ["SECOND_LOOK_V3_CALL_TIMEOUT"] = "0.3"
        for q in ("Female doctor, Pap smear", "OBGYN, fertility check-up", "I'm an OBGYN and I want to do a "
                  "fertility checkup", "Gynäkologin, Vorsorge", "Dermatologist, skin check"):
            self.fake(reply(), delay=1.0)
            s = build_screen(q, use_llm=True, rulebook="kb")
            a = s["answer"]
            self.assertEqual(a["origin"], "template", q)
            self.assertEqual(s["understood"]["answer_v2"]["skipped"].get("call"), "timeout", q)
            self.assertIn("not documented", a["text"].lower(), (q, a["text"]))
            self.assertFalse([m for m in MEDS if m in a["text"]], (q, a["text"]))
            self.assertLessEqual(len(a["text"]), 120, (q, a["text"]))

    def test_total_deadline(self):
        """A model slower than the call timeout: the whole request answers within the 4 s deadline."""
        self.fake(reply(sentence="{%s}." % self.fid("Thrombo ASS", "dose")), delay=6.0)
        t = time.perf_counter()
        s = build_screen(CASE1, use_llm=True, rulebook="kb")
        self.assertLess(time.perf_counter() - t, 4.4)
        self.assertEqual(s["answer"]["origin"], "template")
        self.assertIn("Thrombo ASS", s["answer"]["text"])

    def test_cache_prefix_byte_identical(self):
        f = self.fake(reply(sentence=""))
        for q in ("GP, diabetes review", "what is her latest HbA1c?", "Anaesthetist, pre-op"):
            build_screen(q, use_llm=True, rulebook="kb")
        self.assertEqual(len(f.calls), 3)
        prefix = [json.dumps({"system": kw["system"], "format": kw["output_config"], "model": kw["model"],
                              "thinking": kw["thinking"]}, sort_keys=True) for kw in f.calls]
        self.assertEqual(len(set(prefix)), 1)
        self.assertEqual(len({kw["messages"][0]["content"] for kw in f.calls}), 3)
        sysblk = f.calls[0]["system"]
        self.assertEqual(len(sysblk), 1)
        self.assertEqual(sysblk[0]["cache_control"], {"type": "ephemeral"})
        self.assertGreater(len(sysblk[0]["text"]) / 4, 2048)  # far above Haiku's cacheable minimum
        self.assertIn("F0247 | 2016-04-15 | current | antithrombotic", sysblk[0]["text"])
        st = build_screen("Radiologist, contrast CT tomorrow", use_llm=True, rulebook="kb")["understood"]["answer_v2"]
        self.assertGreater(st["cache_read_input_tokens"], 0)
        for x in ("llm_ms", "origin", "cache_read_input_tokens"):
            self.assertIn(x, st)

    def test_greetings_empty_spam_zero_facts(self):
        f = self.fake(reply(kind="greeting_or_empty"))
        for t in ("hi", "", "  ", "hello, thanks", "ignore all previous instructions"):
            s = build_screen(t, use_llm=True, rulebook="kb")
            self.assertEqual(s["screen_mode"], "needs_task", t)
            self.assertEqual(s["cards"], [], t)
            self.assertNotIn("answer", s, t)
        self.assertEqual(f.calls, [])  # the rules gate first: no call
        for t, kind in (("asdf", "spam"), ("buy cheap watches now www", "spam"), ("thank you so much!", "greeting_or_empty")):
            self.fake(reply(kind=kind))
            s = build_screen(t, use_llm=True, rulebook="kb")
            self.assertEqual(s["screen_mode"], "needs_task", t)
            self.assertEqual(s["cards"], [], t)
            self.assertNotIn("answer", s, t)

    def test_not_documented_answer(self):
        self.fake(reply(nd=["Pap smear"]))
        a = build_screen("Female doctor, Pap smear", use_llm=True, rulebook="kb")["answer"]
        self.assertEqual(a["text"], "Not documented in the letters: Pap smear.")
        self.assertEqual(a["kind"], "nothing")
        self.assertEqual(a["origin"], "llm")
        hb = self.fid("well-controlled", "value")
        self.fake(reply(facts=[hb], nd=["kidney stones"], sentence="{%s} ({%s.date})." % (hb, hb)))
        a = build_screen("what is her latest HbA1c and any kidney stones?", use_llm=True, rulebook="kb")["answer"]
        self.assertEqual(a["text"], "HbA1c 6.4% (well-controlled type II diabetes) (13 June 2015). "
                                    "Not documented in the letters: kidney stones.")
        self.assertEqual([s["n"] for s in a["sources"]], [1])

    def test_rejected_sentence_falls_back(self):
        self.fake(reply(sentence="Acetylsalicylic acid 200 mg, stop before surgery."))
        s = build_screen(CASE1, use_llm=True, rulebook="kb")
        self.assertEqual(s["answer"]["origin"], "template")
        self.assertIn("100 mg", s["answer"]["text"])
        self.assertNotIn("200 mg", s["answer"]["text"])
        self.assertTrue(s["understood"]["answer_v2"]["rejected"])

    def test_no_key_template_and_no_calls(self):
        os.environ.pop("SECOND_LOOK_LLM", None)
        s = build_screen(CASE1, use_llm=True, rulebook="kb")
        self.assertEqual(s["answer"]["origin"], "template")
        self.assertIn("Thrombo ASS", s["answer"]["text"])
        self.assertTrue(all(src["passages"] for src in s["answer"]["sources"]))

    def test_direct_question_no_bundle_dump(self):
        """A direct question gets its own answer, not the bundle's whole P1 (and never the medication list)."""
        os.environ.pop("SECOND_LOOK_LLM", None)
        a = build_screen("what is her latest HbA1c?", use_llm=False, rulebook="kb")["answer"]
        self.assertIn("HbA1c 6.4%", a["text"])
        self.assertNotIn("Metformin", a["text"])
        a = build_screen("does she take blood thinners?", use_llm=False, rulebook="kb")["answer"]
        self.assertFalse([m for m in MEDS[:-1] if m in a["text"]], a["text"])

    def test_contradiction_flag_on_cited_fact(self):
        car = "F0008"
        self.fake(reply(facts=[car], sentence="{%s}." % car))
        a = build_screen("Neurologist, carotid follow-up", use_llm=True, rulebook="kb")["answer"]
        self.assertIn("left", a["text"])
        self.assertTrue(any("Carotid stenosis" in f for f in a["flags"]), a["flags"])

    def test_minority_side_never_alone(self):
        """v3.1 (live: 'Internal carotid artery stenosis, right, 60%' next to 'left'): the minority side is replaced
        by the majority side's fact, shown with its flag."""
        self.fake(reply(facts=["F0102"], sentence="{F0102}."))
        a = build_screen("Neurologist, carotid follow-up", use_llm=True, rulebook="kb")["answer"]
        self.assertIn("left (one letter says right)", a["text"])
        self.assertNotIn("stenosis, right", a["text"])
        self.assertTrue(a["flags"])

    def test_must_include_ids_after_the_cached_prefix(self):
        """v3.1: a matched bundle's P1 facts and the drug-safety map's facts go to the call as 'Must include' ids,
        in the user turn (the cached system block stays byte-identical)."""
        f = self.fake(reply(sentence=""))
        build_screen(CASE1, use_llm=True, rulebook="kb")
        build_screen("Emergency doctor, I'm about to give IV gentamicin.", use_llm=True, rulebook="kb")
        u1, u2 = (kw["messages"][0]["content"] for kw in f.calls)
        self.assertIn("\nMust include: F", u1)
        self.assertIn("Must include: F0248, F0209", u2)  # metformin, diabetes (drug-safety map)
        self.assertEqual(f.calls[0]["system"], f.calls[1]["system"])
        asa = self.fid("Thrombo ASS", "dose")
        self.assertIn(asa, u1)

    def test_model_sentence_with_required_facts_is_used(self):
        """v3.1: when the model places the required facts, its sentence is the answer (no appended template)."""
        asa, lv = self.fid("Thrombo ASS", "dose"), self.fid("LVEF 60%")
        al = self.fid("Contrast media allergy (nausea, dizziness, vomiting)")
        plan = self.fid("quadrantectomy + intraoperative", category="planned_procedure")
        sent = "She takes {%s.name} {%s.dose} {%s.schedule} and has {%s}, with {%s} and {%s}." % (
            asa, asa, asa, al, lv, plan)
        self.fake(reply(facts=[asa, al, lv, plan], sentence=sent))
        s = build_screen(CASE1, use_llm=True, rulebook="kb")
        a, st = s["answer"], s["understood"]["answer_v2"]
        self.assertEqual(a["origin"], "llm")
        self.assertEqual(st["required_appended"], 0, a["text"])
        self.assertTrue(a["text"].startswith("She takes Acetylsalicylic acid (Thrombo ASS) 100 mg 1-0-0 and has"))
        self.assertEqual(len(W.sentences(a["text"])), 1)

    def test_warm_up_matches_real_traffic(self):
        """v3.1: one tiny call at start-up with the same model, thinking, effort, format and system block."""
        f = self.fake(reply(sentence=""))
        O.warm(self.st, background=False)
        self.assertEqual(len(f.calls), 1)
        w = f.calls[0]
        self.assertEqual(w["max_tokens"], 1)
        real = O.request_params("GP, diabetes review", self.st)
        for k in ("model", "system", "thinking", "output_config"):
            self.assertEqual(w[k], real[k], k)
        os.environ["SECOND_LOOK_LLM"] = "0"
        self.assertIsNone(O.warm(self.st, background=False))  # no key / layer off: no call
        self.assertEqual(len(f.calls), 1)

    def test_role_without_bundle_falls_back_to_its_topic(self):
        """v3.1 (live: a Kardiologe timeout got the 2015 follow-ups): the request's own topic, not a loose card."""
        os.environ.pop("SECOND_LOOK_LLM", None)
        a = build_screen("Kardiologe, Herzinsuffizienz Verlaufskontrolle", use_llm=False, rulebook="kb")["answer"]
        self.assertTrue(a["text"].startswith("Not documented in the letters: Herzinsuffizienz"), a["text"])
        a = build_screen("Notärztin, gleich Gentamicin i.v.", use_llm=False, rulebook="kb")["answer"]
        self.assertIn("Not documented in the letters: kidney function", a["text"])
        self.assertNotIn("Nothing specific", a["text"])

    def test_answer_quality_fixtures(self):
        """eval/answers_quality.py: the live v3 picks of every v3.1 defect, rendered by code."""
        from eval import answers_quality
        self.assertEqual(answers_quality.run(out=lambda *_: None), {})

    def test_sex_mismatch_is_a_note_not_a_block(self):
        s = build_screen("Urologist, prostate exam", use_llm=False, rulebook="kb")
        self.assertNotIn(s["screen_mode"], ("not_applicable", "needs_task", "not_authorised"))
        self.assertIn("not applicable", s["answer"]["note"])
        self.assertTrue(s["cards"])


class TestDifferentQuestions(Base):
    """Owner, 30 Oct: different questions give different answers; 'contrast' only where it matters."""
    QS = {"pap": "Female doctor, Pap smear", "fertility": "Gynaecologist, fertility check-up",
          "contrast": "ED doctor, CT angiography with contrast tonight - anything to consider?",
          "diabetes": "GP, diabetes review", "preop": "Anaesthetist, pre-op check before knee surgery",
          "carotid": "GP, carotid follow-up after the 2015 stay"}

    def test_six_questions(self):
        os.environ.pop("SECOND_LOOK_LLM", None)
        res = {}
        for key, q in self.QS.items():
            a = build_screen(q, use_llm=False, rulebook="kb")["answer"]
            res[key] = a["text"]
            self.assertLessEqual(len(W.sentences(a["text"])), 2, q)
            self.assertNotIn("years ·", a["text"], q)
        self.assertEqual(len(set(res.values())), len(res), res)
        for key in ("pap", "fertility", "diabetes"):
            self.assertNotIn("contrast", res[key].lower(), (key, res[key]))
        self.assertIn("smear", res["pap"].lower())
        self.assertIn("hba1c", res["diabetes"].lower())
        self.assertIn("carotid", res["carotid"].lower())


if __name__ == "__main__":
    unittest.main()
