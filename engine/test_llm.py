"""LLM understand layer with a mocked Anthropic client (no API key, no network).

    python3 -m unittest engine.test_llm
"""
import json
import os
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace

from engine import llm, llm_budget
from engine.kb import kb as load_kb
from engine.screen import build_screen

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAS_DATA = os.path.exists(os.path.join(ROOT, "data", "build", "facts.json")) or \
    os.path.isdir(os.path.join(ROOT, "data", "patient-0000-0001", "documents"))


class FakeMessages:
    def __init__(self, answer, delay=0.0, usage=None, stop_reason="end_turn"):
        self.answer, self.delay, self.stop_reason = answer, delay, stop_reason
        self.usage = usage or dict(input_tokens=40, output_tokens=120, cache_creation_input_tokens=0,
                                   cache_read_input_tokens=1900)
        self.calls = []

    def create(self, **kw):
        self.calls.append(kw)
        if self.delay:
            time.sleep(self.delay)
        ans = self.answer(kw) if callable(self.answer) else self.answer
        text = ans if isinstance(ans, str) else json.dumps(ans)
        return SimpleNamespace(content=[SimpleNamespace(type="thinking", thinking=""),
                                        SimpleNamespace(type="text", text=text)],
                               stop_reason=self.stop_reason, usage=SimpleNamespace(**self.usage))


class FakeClient:
    def __init__(self, *a, **kw):
        self.messages = FakeMessages(*a, **kw)


class LLMTestBase(unittest.TestCase):
    ENV = ("SECOND_LOOK_LLM", "SECOND_LOOK_LLM_BUDGET_EUR", "SECOND_LOOK_LLM_MAX_CALLS_PER_DAY",
           "SECOND_LOOK_LLM_TIMEOUT", "SECOND_LOOK_LLM_BUDGET_FILE", "SECOND_LOOK_LLM_MODEL")

    def setUp(self):
        self.saved = {k: os.environ.get(k) for k in self.ENV}
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["SECOND_LOOK_LLM"] = "1"
        os.environ.pop("SECOND_LOOK_LLM_MODEL", None)
        llm_budget.reset(os.path.join(self.tmp.name, "llm_budget.json"))
        self.kb = load_kb()

    def tearDown(self):
        llm.set_client(None)
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        llm_budget.reset()
        self.tmp.cleanup()

    def client(self, answer, **kw):
        c = FakeClient(answer, **kw)
        llm.set_client(c)
        return c.messages


class TestRequestAndValidation(LLMTestBase):
    def test_request_shape(self):
        fake = self.client({"role_id": "gp", "bundle_ids": ["B03"], "reason": "GP reviewing diabetes"})
        prop, info = llm.propose("GP here, sugar check", self.kb)
        self.assertEqual(prop, {"role_id": "gp", "bundle_ids": ["B03"], "reason": "GP reviewing diabetes",
                                "focus_concepts": []})
        self.assertTrue(info["called"])
        kw = fake.calls[0]
        self.assertEqual(kw["model"], "claude-haiku-5-5")
        for banned in ("temperature", "top_p", "top_k", "tool_choice", "tools"):
            self.assertNotIn(banned, kw)
        self.assertEqual(kw["messages"][-1]["role"], "user")  # no assistant prefill
        self.assertEqual(kw["system"][0]["cache_control"], {"type": "ephemeral"})
        fmt = kw["output_config"]["format"]
        self.assertEqual(fmt["type"], "json_schema")
        props = fmt["schema"]["properties"]
        self.assertEqual(set(props["role_id"]["enum"]), {r["id"] for r in self.kb.roles} | {"none"})
        self.assertEqual(set(props["bundle_ids"]["items"]["enum"]),
                         {b["id"] for b in self.kb.bundles} - {self.kb.fallback_bundle})
        self.assertFalse(fmt["schema"]["additionalProperties"])
        # static part is small (~4 chars/token) and identical across requests (cacheable prefix)
        self.assertLess(len(kw["system"][0]["text"]) / 4, 2500)
        llm.propose("another situation", self.kb)
        self.assertEqual(fake.calls[1]["system"], kw["system"])
        self.assertEqual(fake.calls[1]["output_config"], kw["output_config"])

    def test_model_override(self):
        os.environ["SECOND_LOOK_LLM_MODEL"] = "claude-sonnet-5-5"
        fake = self.client({"role_id": "none", "bundle_ids": [], "reason": ""})
        llm.propose("x", self.kb)
        self.assertEqual(fake.calls[0]["model"], "claude-sonnet-5-5")

    def test_invalid_ids_dropped(self):
        self.client({"role_id": "astronaut", "bundle_ids": ["B99", "B03", "B03", "B18", "B07", "B09", "B10"],
                     "reason": "x" * 500})
        prop, _ = llm.propose("something", self.kb)
        self.assertIsNone(prop["role_id"])
        self.assertEqual(prop["bundle_ids"], ["B03", "B07", "B09"])  # fallback bundle dropped, max 3
        self.assertLessEqual(len(prop["reason"]), llm.MAX_REASON)

    def test_garbage_and_refusal(self):
        self.client("not json")
        self.assertIsNone(llm.propose("a", self.kb)[0])
        self.client({"role_id": "gp", "bundle_ids": [], "reason": ""}, stop_reason="refusal")
        prop, info = llm.propose("b", self.kb)
        self.assertIsNone(prop)
        self.assertIn("refusal", info["skipped"])

    def test_disabled(self):
        fake = self.client({"role_id": "gp", "bundle_ids": [], "reason": ""})
        os.environ["SECOND_LOOK_LLM"] = "0"
        self.assertEqual(llm.propose("a", self.kb), (None, {"called": False, "cached": False,
                                                            "skipped": "disabled", "cost_eur": 0.0}))
        self.assertEqual(fake.calls, [])


class TestBudgetAndCache(LLMTestBase):
    def test_cache_hit(self):
        fake = self.client({"role_id": "gp", "bundle_ids": ["B03"], "reason": "r"})
        p1, i1 = llm.propose("GP,  Diabetes review", self.kb)
        p2, i2 = llm.propose("gp, diabetes   REVIEW ", self.kb)
        self.assertEqual(p1, p2)
        self.assertEqual(len(fake.calls), 1)
        self.assertTrue(i2["cached"])
        self.assertEqual(llm_budget.budget().snapshot()["calls_today"], 1)

    def test_cost_counted_from_usage(self):
        self.client({"role_id": "gp", "bundle_ids": [], "reason": ""},
                    usage=dict(input_tokens=1_000_000, output_tokens=1_000_000, cache_creation_input_tokens=0,
                               cache_read_input_tokens=0))
        _p, info = llm.propose("a", self.kb)
        self.assertAlmostEqual(info["cost_eur"], 0.10 + 0.50)  # Haiku 5.5 list price, USD counted as EUR
        s = llm_budget.budget().snapshot()
        self.assertAlmostEqual(s["spend_eur"], 0.60)
        self.assertEqual(s["input_tokens"], 1_000_000)
        with open(os.environ["SECOND_LOOK_LLM_BUDGET_FILE"], encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["calls_today"], 1)
        # a restart reads the counters back
        self.assertAlmostEqual(llm_budget.reset().snapshot()["spend_eur"], 0.60)

    def test_budget_cap_stops_calls(self):
        os.environ["SECOND_LOOK_LLM_BUDGET_EUR"] = "0.5"
        fake = self.client({"role_id": "gp", "bundle_ids": [], "reason": ""},
                           usage=dict(input_tokens=1_000_000, output_tokens=1_000_000))
        self.assertIsNotNone(llm.propose("first", self.kb)[0])
        prop, info = llm.propose("second", self.kb)
        self.assertIsNone(prop)
        self.assertEqual(info["skipped"], "budget")
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(llm.status()["stopped"], "budget")

    def test_daily_cap_stops_calls(self):
        os.environ["SECOND_LOOK_LLM_MAX_CALLS_PER_DAY"] = "2"
        fake = self.client({"role_id": "gp", "bundle_ids": [], "reason": ""})
        for t in ("a", "b", "c", "d"):
            llm.propose(t, self.kb)
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(llm.propose("e", self.kb)[1]["skipped"], "daily_cap")

    def test_timeout_falls_back(self):
        os.environ["SECOND_LOOK_LLM_TIMEOUT"] = "0.2"
        self.client({"role_id": "gp", "bundle_ids": ["B03"], "reason": ""}, delay=1.0)
        t0 = time.perf_counter()
        prop, info = llm.propose("slow one", self.kb)
        self.assertLess(time.perf_counter() - t0, 0.8)
        self.assertIsNone(prop)
        self.assertEqual(info["skipped"], "timeout")

    def test_exception_falls_back(self):
        class Boom:
            class messages:
                @staticmethod
                def create(**kw):
                    raise ConnectionError("down")
        llm.set_client(Boom())
        prop, info = llm.propose("a", self.kb)
        self.assertIsNone(prop)
        self.assertIn("ConnectionError", info["skipped"])


@unittest.skipUnless(HAS_DATA, "no patient data")
class TestMergeAndGate(LLMTestBase):
    def screen(self, text):
        return build_screen(text, use_llm=True, detail="short", rulebook="kb")

    def test_clear_match_keeps_rules_and_adds(self):
        rules = build_screen("Anaesthetist, pre-op check before breast surgery", use_llm=False, rulebook="kb")
        self.client({"role_id": "surgeon", "bundle_ids": ["B07"], "reason": "pre-op check, review meds"})
        u = self.screen("Anaesthetist, pre-op check before breast surgery")["understood"]
        self.assertEqual(u["role_id"], "anaesthetist")  # alias match beats the model's role
        self.assertTrue(set(rules["understood"]["bundles_chosen"]) <= set(u["bundles_chosen"]))
        self.assertIn("B07", u["bundles_chosen"])
        self.assertTrue(u["llm_used"])
        self.assertEqual(u["llm_reason"], "pre-op check, review meds")

    def test_unrecognised_task_filled_by_llm(self):
        text = "GP here, she mentioned feeling thirsty all the time"
        rules = build_screen(text, use_llm=False, rulebook="kb")["understood"]
        self.client({"role_id": "gp", "bundle_ids": ["B03"], "reason": "Thirst suggests checking diabetes"})
        s = self.screen(text)
        u = s["understood"]
        self.assertEqual(u["role_id"], "gp")
        self.assertIn("B03", u["bundles_chosen"])
        self.assertNotEqual(s["screen_mode"], "not_authorised")
        if rules["tasks_from"] in ("fallback", "role_default"):
            self.assertTrue(u["llm_used"])

    def test_no_role_llm_role_does_not_authorise(self):
        self.client({"role_id": "gp", "bundle_ids": ["B07"], "reason": "general question"})
        for text in ("tell me everything about her", "what is wrong with her?"):
            s = self.screen(text)
            self.assertEqual(s["screen_mode"], "not_authorised", text)
            self.assertEqual(s["cards"], [])

    def test_non_clinical_still_blocked(self):
        self.client({"role_id": "gp", "bundle_ids": ["B03", "B07"], "reason": "neighbour asks about meds"})
        for text in ("I'm her neighbour, which tablets does she take?", "Journalist here, what is her diagnosis"):
            s = self.screen(text)
            self.assertEqual(s["screen_mode"], "not_authorised", text)
            self.assertEqual(s["cards"], [])

    def test_timeout_gives_rules_result(self):
        os.environ["SECOND_LOOK_LLM_TIMEOUT"] = "0.2"
        text = "Anaesthetist, pre-op check before breast surgery"
        rules = build_screen(text, use_llm=False, rulebook="kb")["understood"]
        self.client({"role_id": "gp", "bundle_ids": ["B10"], "reason": ""}, delay=1.0)
        u = self.screen(text)["understood"]
        self.assertEqual(u["bundles_chosen"], rules["bundles_chosen"])
        self.assertFalse(u["llm_used"])
        self.assertEqual(u["llm"]["skipped"], "timeout")

    def test_briefing_routing_fields(self):
        sys.path.insert(0, os.path.join(ROOT, "backend"))
        from app import adapter
        self.client({"role_id": "gp", "bundle_ids": ["B09"], "reason": "Blood pressure follow-up"})
        b = adapter.build_briefing("GP, how is her blood pressure doing", use_llm=True)
        self.assertIn("llm_used", b.routing)
        if b.routing["llm_used"]:
            self.assertEqual(b.routing["llm_reason"], "Blood pressure follow-up")
        b2 = adapter.build_briefing("GP, how is her blood pressure doing", use_llm=False)
        self.assertFalse(b2.routing["llm_used"])
        self.assertIsNone(b2.routing["llm_reason"])


@unittest.skipUnless(HAS_DATA, "no patient data")
class TestFocusConcepts(LLMTestBase):
    """focus_concepts: an enum of the record's concept labels; validated in code; promoted after the gate."""

    def setUp(self):
        super().setUp()
        from engine.focus import concepts
        from engine.screen import store
        self.labels, self.by_label = concepts(store())
        self.sle = next(x for x in self.labels if "lupus" in x.lower())

    def test_schema_enum_is_the_record_concepts(self):
        system, schema, _r, _b, conc = llm.static_prompt(self.kb, self.labels)
        prop = schema["properties"]["focus_concepts"]
        self.assertEqual(prop["items"]["enum"], list(self.labels))
        self.assertIn("focus_concepts", schema["required"])
        self.assertIn(self.sle, system)
        self.assertLessEqual(max(len(x) for x in self.labels), 80)
        # without concepts the request is unchanged (no focus field)
        self.assertNotIn("focus_concepts", llm.static_prompt(self.kb)[1]["properties"])

    def test_validation_keeps_only_record_labels_max_five(self):
        raw = {"role_id": "gp", "bundle_ids": ["B07"], "reason": "x",
               "focus_concepts": ["Invented disease", self.sle, self.sle, 42] + list(self.labels[:8])}
        out = llm.validate(raw, self.kb, self.labels)
        self.assertEqual(out["focus_concepts"][0], self.sle)
        self.assertLessEqual(len(out["focus_concepts"]), llm.MAX_FOCUS)
        self.assertNotIn("Invented disease", out["focus_concepts"])
        self.assertTrue(all(x in self.labels for x in out["focus_concepts"]))
        self.assertEqual(llm.validate(dict(raw, focus_concepts="lupus"), self.kb, self.labels)["focus_concepts"], [])
        self.assertEqual(llm.validate(raw, self.kb, ())["focus_concepts"], [])  # no enum -> nothing accepted

    def test_request_carries_the_enum(self):
        fake = self.client({"role_id": "none", "bundle_ids": [], "reason": "r", "focus_concepts": []})
        llm.propose("Dermatologist, skin check", self.kb, self.labels)
        kw = fake.calls[0]
        self.assertEqual(kw["output_config"]["format"]["schema"]["properties"]["focus_concepts"]["items"]["enum"],
                         list(self.labels))

    def test_focus_promoted_into_short_view(self):
        self.client({"role_id": "none", "bundle_ids": [], "reason": "Autoimmune disease matters for skin lesions",
                     "focus_concepts": [self.sle, "Not a record label"]})
        s = build_screen("Dermatologist checking a mole on her back", use_llm=True, detail="short", rulebook="kb")
        card = next(c for c in s["focus"] if c["need"] == "llm_focus")
        self.assertEqual(card["label_en"], "AI-highlighted for this task")
        self.assertTrue(set(card["facts"]) <= set(self.by_label[self.sle]))
        self.assertEqual(card["why"], "Autoimmune disease matters for skin lesions")
        u = s["understood"]
        self.assertEqual(u["llm_focus"]["concepts"], [self.sle])
        self.assertTrue(u["llm_used"])
        sys.path.insert(0, os.path.join(ROOT, "backend"))
        from app import adapter
        b = adapter.build_briefing("Dermatologist checking a mole on her back", use_llm=True)
        self.assertEqual(b.routing["llm_focus"]["concepts"], [self.sle])
        need = next(n for n in b.needs if n.need == "llm_focus")
        self.assertTrue(any("lupus" in f.label_en.lower() for f in need.facts))

    def test_focus_still_gated(self):
        self.client({"role_id": "gp", "bundle_ids": ["B07"], "reason": "x", "focus_concepts": [self.sle]})
        s = build_screen("I'm her neighbour, does she have lupus?", use_llm=True, detail="short", rulebook="kb")
        self.assertEqual(s["screen_mode"], "not_authorised")
        self.assertEqual(s["cards"], [])
        self.assertFalse(s.get("focus"))

    def test_rules_only_has_no_llm_focus(self):
        s = build_screen("Radiation oncologist, IORT planning", use_llm=False, detail="short", rulebook="kb")
        self.assertIsNone(s["understood"].get("llm_focus"))
        tf = next(c for c in s["focus"] if c["need"] == "task_focus")  # overlay TR02, deterministic
        self.assertIn("TR02", tf["overlay_entries"])
        self.assertEqual(tf["sources"][0]["id"], "TODO-cite")


class TestTaskTermFocus(unittest.TestCase):
    @unittest.skipUnless(HAS_DATA, "no patient data")
    def test_task_terms(self):
        for text, word in (("Gastroenterologist, reflux symptoms", "reflux"),
                           ("Endocrinologist, osteoporosis treatment", "osteoporosis"),
                           ("Pulmonologist, sleep apnoea follow-up", "apnoea")):
            s = build_screen(text, use_llm=False, detail="short", rulebook="kb")
            labels = " ".join(it["label_en"].lower() for c in s["focus"] for it in c["items"])
            with self.subTest(text=text):
                self.assertIn(word, labels)


if __name__ == "__main__":
    unittest.main()
