"""Relevance tests:  python3 -m unittest engine.test_relevance -v

The screen shows only what the task needs:
* sex-specific tasks (rulebook/applicability.json): a task for the other sex gets a first card
  'not applicable' linked to the passage that documents the patient's sex, then only a safety summary
* an unrecognised task gets a short safety summary and a note with 3 suggested tasks, never a dump
* list cards are deduplicated (one item per concept / allergen), without ruled-out findings or open
  questions, at most 8 items in the short view
* blind spot, contradictions and open follow-ups only when they touch the screen
* the 15 expected answers stay on screen in the short and the long view
"""
import json
import os
import unittest

from eval.core import Build, attrs_text, eval_question, norm

from engine import applicability as A
from engine.data import ROOT, store
from engine.fill import LIST_LIMIT_SHORT, concept_key, is_question
from engine.screen import MAX_SUMMARY_CARDS, build_screen
from engine.test_engine import SITUATIONS, card_facts

MODES = ("short", "long")


def screen(text, detail="short"):
    return build_screen(text, use_llm=False, detail=detail, rulebook="kb")


def slots(s):
    return [c["slot"] for c in s["cards"]]


class _Store:
    """Minimal stand-in record for the sex detection."""

    def __init__(self, texts):
        self.passages = [{"id": "d:p%04d" % i, "text": t} for i, t in enumerate(texts)]


class TestNotApplicable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = store()
        cls.s = {d: screen("GP, prostate exam", d) for d in MODES}

    def test_first_card_not_applicable_with_source(self):
        for d, s in self.s.items():
            with self.subTest(detail=d):
                first = s["cards"][0]
                self.assertEqual(first["status"], "not_applicable")
                self.assertIn("female", first["value_en"])
                self.assertTrue(first["passages"])
                p = self.st.passage_by_id[first["passages"][0]]
                self.assertRegex(p["text"], r"\b(Patientin|Frau)\b")
                self.assertEqual(s["screen_mode"], "not_applicable")

    def test_only_a_safety_summary(self):
        for d, s in self.s.items():
            with self.subTest(detail=d):
                self.assertLessEqual(len(s["cards"]), MAX_SUMMARY_CARDS)
                self.assertNotIn("diagnoses_all", slots(s))
                self.assertLessEqual(set(slots(s)[1:]), {"age_sex", "allergies", "med_antithrombotic", "med_current"})
                self.assertIsNone(s["blind_spot"])
                self.assertEqual(s["contradictions"], [])
                self.assertEqual(s["open_followups"], [])
                self.assertGreater(s["other_record_issues"], 0)

    def test_german_wording(self):
        s = screen("Hausarzt: Prostatauntersuchung und PSA")
        self.assertEqual(s["cards"][0]["status"], "not_applicable")


class TestUnrecognisedTask(unittest.TestCase):
    def test_toenail(self):
        for d in MODES:
            s = screen("GP, ingrown toenail", d)
            with self.subTest(detail=d):
                self.assertLessEqual(len(s["cards"]), MAX_SUMMARY_CARDS)
                self.assertEqual(s["screen_mode"], "fallback")
                u = s["understood"]
                self.assertIn("Task not recognised", u["fallback_note"])
                self.assertEqual(len(u["suggestions"]), 3)
                for title in u["suggestions"]:
                    self.assertIn(title, u["fallback_note"])
                self.assertNotIn("diagnoses_all", slots(s))
                self.assertIsNone(s["blind_spot"])


class TestLists(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.st = store()

    def _diagnoses(self, d):
        s = screen("Ward nurse, admission and discharge handover", d)
        return next(c for c in s["cards"] if c["slot"] == "diagnoses_all")

    def test_diagnoses_short(self):
        c = self._diagnoses("short")
        shown = [it for it in c["items"] if not it.get("collapsed")]
        self.assertLessEqual(len(shown), LIST_LIMIT_SHORT)
        self.assertGreater(c["more"], 0)
        # the rest stays on the card, collapsed behind '+N more' (never dropped from the response)
        self.assertEqual(len(c["items"]) - len(shown), c["more"])
        self.assertIn("more", c["value_en"])
        self._clean(c)

    def test_diagnoses_long(self):
        short, c = self._diagnoses("short"), self._diagnoses("long")
        self.assertEqual(c["more"], 0)
        self.assertEqual(len(c["items"]), len(short["items"]))  # short: shown + collapsed
        self.assertFalse(any(it.get("collapsed") for it in c["items"]))
        self._clean(c)

    def _clean(self, c):
        keys = []
        for it in c["items"]:
            fs = [self.st.fact_by_id[x] for x in it["facts"]]
            rep = fs[-1]
            self.assertNotEqual((rep.get("attrs") or {}).get("assertion"), "negative", it["label_en"])
            self.assertFalse(is_question(rep), it["label_en"])
            self.assertFalse(it["label_en"].rstrip().endswith("?"))
            self.assertFalse(it["label_en"].lower().startswith(("no ", "question")), it["label_en"])
            keys.append(concept_key(rep))
        self.assertEqual(len(keys), len(set(keys)), "duplicate concepts")
        labels = [norm(it["label_en"]) for it in c["items"]]
        self.assertEqual(len(labels), len(set(labels)), "duplicate labels")

    def test_active_first(self):
        c = self._diagnoses("long")
        active = [it.get("status") == "current" for it in c["items"]]
        self.assertEqual(active, sorted(active, reverse=True))

    def test_one_item_per_allergen(self):
        s = screen(SITUATIONS["1"])
        c = next(c for c in s["cards"] if c["slot"] == "allergies")
        subs = [str((self.st.fact_by_id[it["facts"][-1]].get("attrs") or {}).get("substance")) for it in c["items"]]
        self.assertEqual(len(subs), len(set(subs)))
        self.assertGreater(len(c["items"][0]["passages"]), 1)  # other mentions stay as source links


class TestTaskScope(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "eval", "answer_keys.json"), encoding="utf-8") as fh:
            cls.keys = json.load(fh)
        cls.st = store()
        cls.s = {(sid, d): screen(t, d) for sid, t in SITUATIONS.items() for d in MODES}

    def _answers(self, s, qids):
        facts = [self.st.fact_by_id[x] for x in card_facts(s)]
        facts += [self.st.fact_by_id[x] for i in (s.get("blind_spot") or {}).get("items") or []
                  for x in i.get("facts") or [] if x in self.st.fact_by_id]
        b = Build(self.st.docs, self.st.passages, list({f["id"]: f for f in facts}.values()))
        texts = {f["id"]: norm((f.get("label_en") or "") + " | " + attrs_text(f.get("attrs") or {})) for f in facts}
        return [q for q in qids if not eval_question(b, q, self.keys[q], texts)["pass"]]

    def test_anaesthetist_short_answers(self):
        s = self.s[("1", "short")]
        self.assertEqual(self._answers(s, ["1.1", "1.2", "1.3"]), [])
        self.assertLessEqual(len(s["cards"]), 12)

    def test_15_answers_short_and_long(self):
        for d in MODES:
            for sid in SITUATIONS:
                with self.subTest(sid=sid, detail=d):
                    qids = sorted(q for q in self.keys if q.startswith(sid + "."))
                    self.assertEqual(self._answers(self.s[(sid, d)], qids), [])

    def test_issues_touch_the_screen(self):
        for (sid, d), s in self.s.items():
            shown = {x for c in s["cards"] for x in c["facts"]}
            on_card = {x for c in s["cards"] for x in c.get("conflicts") or []}
            with self.subTest(sid=sid, detail=d):
                for c in s["contradictions"]:
                    self.assertTrue(set(c["facts"]) & shown or c["id"] in on_card, c["id"])
                total = len(s["contradictions"]) + len(s["contradictions_other"])
                self.assertEqual(total, 8)
                bs = s["blind_spot"]
                if bs:
                    self.assertTrue(bs["items"])
                n_bs = len((bs or {}).get("items") or [])
                self.assertEqual(s["other_record_issues"],
                                 len(s["contradictions_other"]) + len(s["blind_spot_other"])
                                 + len(s["open_followups_other"]))
                self.assertEqual(n_bs + len(s["blind_spot_other"]), len(store().compare["blind_spots"]))

    def test_followups_screen(self):
        s = self.s[("5", "short")]
        self.assertTrue(s["open_followups"])
        self.assertTrue(s["blind_spot"])
        s = self.s[("2", "short")]
        self.assertIsNone(s["blind_spot"])  # nothing the surgeon's short screen shows was dropped

    def test_short_default(self):
        self.assertEqual(build_screen(SITUATIONS["1"], use_llm=False)["detail"], "short")


class TestUnseenSituations(unittest.TestCase):
    """Six situations outside the 5 cases: other sex-specific organs and tests, mixed and unknown tasks."""

    def test_testicular_exam_not_applicable(self):
        s = screen("You are the GP. Testicular examination (Hodenuntersuchung).")
        self.assertEqual(s["cards"][0]["status"], "not_applicable")
        self.assertLessEqual(len(s["cards"]), MAX_SUMMARY_CARDS)

    def test_gynaecological_exam_applicable(self):
        for d in MODES:
            s = screen("Gynaecologist, routine gynaecological examination", d)
            with self.subTest(detail=d):
                self.assertEqual(s["screen_mode"], "sex_specific")
                self.assertFalse(any(c["status"] == "not_applicable" for c in s["cards"]))
                self.assertIn("age_sex", slots(s))
                checks = [c for c in s["cards"] if c["shape"] == "record_check"]
                self.assertTrue(checks)
                for c in checks:  # never guessed: what was searched is stated
                    if c["status"] == "not_documented":
                        self.assertTrue(c["searched"]["terms"])
                self.assertTrue(all(c["priority"] == "P1" for c in s["cards"]))
                self.assertLessEqual(len(s["cards"]), 8)
                self.assertIsNone(s["blind_spot"])

    def test_pregnancy_test_german(self):
        s = screen("Hausärztin: Schwangerschaftstest vor Beginn einer neuen Therapie")
        self.assertEqual(s["screen_mode"], "sex_specific")
        self.assertIn("pregnancy", [i["id"] for i in s["understood"]["applicability"]["items"]])
        self.assertLessEqual(len(s["cards"]), MAX_SUMMARY_CARDS)

    def test_mammography_found_in_record(self):
        s = screen("Radiologist, screening mammography")
        self.assertIn("oncology_imaging", slots(s))
        chk = next(c for c in s["cards"] if c["shape"] == "record_check")
        self.assertEqual(chk["status"], "consistent")
        self.assertTrue(chk["facts"] and chk["passages"])

    def test_mixed_task_keeps_the_applicable_part(self):
        s = screen("GP reviewing her diabetes and ordering a PSA test")
        self.assertEqual(s["cards"][0]["status"], "not_applicable")
        self.assertEqual(s["understood"]["bundle_ids"], ["B03"])
        self.assertIn("med_antidiabetic", slots(s))

    def test_unknown_role_and_task(self):
        s = screen("Dermatologist checking a mole on her back")
        self.assertEqual(s["screen_mode"], "fallback")
        self.assertIn("not recognised", s["understood"]["fallback_note"])
        self.assertLessEqual(len(s["cards"]), MAX_SUMMARY_CARDS)

    def test_overview_request(self):
        s = screen("Covering doctor at the weekend, needs a quick overview.")
        self.assertEqual(s["screen_mode"], "overview")
        dx = next(c for c in s["cards"] if c["slot"] == "diagnoses_all")
        self.assertLessEqual(len([it for it in dx["items"] if not it.get("collapsed")]), LIST_LIMIT_SHORT)


class TestSexDetection(unittest.TestCase):
    """Other sexes, on a stand-in record (the demo patient is female)."""

    def test_male_record(self):
        st = _Store(["Sehr geehrter Herr Kollege,", "Herr M. wurde aufgenommen.", "Der Patient ist stabil."])
        res = A.check("pregnancy test", st)
        self.assertEqual(res["sex"], "male")
        self.assertEqual([r["id"] for r in res["not_applicable"]], ["pregnancy"])
        self.assertEqual(A.check("prostate exam", st)["not_applicable"], [])
        card = A.not_applicable_card(st, res["not_applicable"][0], res["sex"], res["passage"], res["word"])
        self.assertEqual(card["value_en"], "Not applicable: the record documents a male patient")
        self.assertTrue(card["passages"])

    def test_unknown_sex_never_guessed(self):
        st = _Store(["Der Patient ist stabil.", "Blutdruck 140/90 mmHg."])
        res = A.check("prostate exam", st)
        self.assertIsNone(res["sex"])
        self.assertEqual(res["not_applicable"], [])
        self.assertEqual([r["id"] for r in res["applicable"]], ["prostate"])

    def test_female_wins_specific_word(self):
        sex, pid, word = A.documented_sex(store())
        self.assertEqual(sex, "female")
        self.assertEqual(word, "Patientin")


if __name__ == "__main__":
    unittest.main()


class TestCompactShortView(unittest.TestCase):
    """Short view on a phone: P2 cards and trends collapse to a few open items; nothing leaves the response."""

    def test_also_relevant_capped_and_kept(self):
        from engine.kbfill import ALSO_VISIBLE
        s = screen("General practitioner, weight review for type 2 diabetes")
        for c in s.get("also_relevant") or []:
            items = c.get("items") or []
            shown = [it for it in items if not it.get("collapsed")]
            if c.get("shape") != "trend":
                self.assertLessEqual(len(shown), ALSO_VISIBLE, c["slot"])
            self.assertEqual(c.get("collapsed", 0), len(items) - len(shown))
            for it in items:  # collapsed items keep their source passages
                self.assertTrue(it["passages"], c["slot"])

    def test_bp_trend_dedupe_and_ends_open(self):
        s = screen("General practitioner, weight review for type 2 diabetes")
        vit = next((c for c in s["cards"] + (s.get("also_relevant") or []) if c["slot"] == "vitals_bp_hr"), None)
        if vit is None:
            self.skipTest("vitals not on this screen")
        bp = [it for it in vit["items"] if it["label_en"].lower().startswith("blood pressure")]
        keys = [(it["date"][:10], it["label_en"].split("(")[0].strip()) for it in bp]
        self.assertEqual(len(keys), len(set(keys)), "same-day identical readings are merged")
        self.assertFalse(bp[0].get("collapsed"))
        self.assertFalse(bp[-1].get("collapsed"))
        self.assertTrue(any(it.get("collapsed") for it in bp[1:-1]))

    def test_weight_series_all_open(self):
        s = screen("General practitioner, how did her weight change between June 2015 and April 2016")
        w = next(c for c in s["cards"] + (s.get("also_relevant") or []) if c["slot"] == "weight")
        self.assertEqual(len(w["items"]), 3)
        self.assertFalse(any(it.get("collapsed") for it in w["items"]))  # 78 -> 67 -> 66 kg all visible
