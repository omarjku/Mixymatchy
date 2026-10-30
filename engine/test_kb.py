"""Routing knowledge base tests:  python3 -m unittest engine.test_kb -v

* the KB + slot map load without errors, and the validator catches broken IDs (refuses to start)
* validation.demo_coverage from the KB: each listed question's slots appear at the stated priority
  for the 5 case situations (and in the short screen when P1)
* receptors are absent from the anaesthetist's screen and present on the surgeon's short screen
* B04 implies B05
* 8 roles that are not in the 5 cases (dentist, physio, dietitian, paramedic, pharmacist, radiation
  oncologist, ophthalmologist, ward nurse), with the KB's own hold-out situations, give non-empty screens
* short mode stays under ~12 cards; long mode contains the short screen
* every card carries slot id, label, shape, priority, why, guideline sources, status, facts/passages
"""
import copy
import json
import re
import unittest

from engine import kb as kbmod
from engine.data import store
from engine.fill import _d, _dob, age_years
from engine.route import expand
from engine.screen import build_screen
from engine.test_engine import SITUATIONS

SHORT_MAX = 12
UNSEEN_ROLES = {"dentist": "Dentist", "physio": "Physiotherapist", "dietitian": "Dietitian",
                "paramedic_triage": "Paramedic", "pharmacist": "Pharmacist",
                "radiation_oncologist": "Radiation oncologist", "ophthalmologist": "Ophthalmologist",
                "ward_nurse": "Ward nurse"}


def screen(text, detail="long"):
    return build_screen(text, use_llm=False, detail=detail, rulebook="kb")


class TestValidation(unittest.TestCase):
    def test_kb_loads_without_errors(self):
        k = kbmod.load()
        self.assertEqual(k.errors, [])
        self.assertEqual(set(k.slot_by_id), set(k.slot_map["slots"]))

    def test_broken_ids_refuse_to_start(self):
        with open(kbmod.KB_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        with open(kbmod.SLOT_MAP_PATH, encoding="utf-8") as fh:
            smap = json.load(fh)
        bad = copy.deepcopy(data)
        bad["bundles"][0]["slots"]["P1"].append("no_such_slot")
        bad["bundles"][1]["implies"] = ["B99"]
        bad["roles"][0]["default_bundles"].append("B98")
        bad["roles"][0]["modifiers"].append({"slot": "ghost", "priority": "P1"})
        bad["rules"][0]["surface"].append("phantom")
        bad["bundles"][2]["sources"].append("G99")
        bad["bundles"][3]["rules"].append("R99")
        bad_map = copy.deepcopy(smap)
        del bad_map["slots"]["airway"]
        k = kbmod.KB(bad, bad_map)
        errors, _ = k.validate()
        text = "\n".join(errors)
        for needle in ("unknown slot no_such_slot", "unknown bundle B99", "unknown default bundle B98",
                       "unknown slot ghost", "unknown slot phantom", "unknown guideline G99", "unknown rule R99",
                       "no entry for slot airway"):
            self.assertIn(needle, text)
        with self.assertRaises(kbmod.KBError) as cm:
            if errors:
                raise kbmod.KBError(errors)
        self.assertGreaterEqual(len(cm.exception.errors), 8)

    def test_source_ids(self):
        self.assertEqual(kbmod.source_ids("G02,G03,G07"), ["G02", "G03", "G07"])
        self.assertEqual(kbmod.source_ids("L10 (production), L02-L04 (prototype)"), ["L10", "L02", "L03", "L04"])
        self.assertEqual(kbmod.source_ids("code only"), [])


class TestDemoSituations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.k = kbmod.kb()
        cls.long = {sid: screen(t) for sid, t in SITUATIONS.items()}
        cls.short = {sid: screen(t, "short") for sid, t in SITUATIONS.items()}

    def test_demo_coverage(self):
        rows = self.k.data["validation"]["demo_coverage"]
        self.assertEqual(len(rows), 15)
        for row in rows:
            sid = row["question"].split(".")[0]
            want = re.match(r"(B\d+)\s+(P\d)", row["where"]).group(2)
            slots = {s["slot"]: s["priority"] for s in self.long[sid]["understood"]["slots"]}
            long_cards = {c["slot"] for c in self.long[sid]["cards"]}
            short_cards = {c["slot"] for c in self.short[sid]["cards"]}
            for slot in row["slots"]:
                with self.subTest(q=row["question"], slot=slot):
                    self.assertEqual(slots.get(slot), want, "%s %s" % (row["question"], row["where"]))
                    self.assertIn(slot, long_cards)
                    if want == "P1":
                        self.assertIn(slot, short_cards)

    def test_routing_of_the_cases(self):
        u = {sid: s["understood"] for sid, s in self.long.items()}
        self.assertEqual((u["1"]["role_id"], u["1"]["bundle_ids"]), ("anaesthetist", ["B01"]))
        self.assertEqual((u["2"]["role_id"], u["2"]["bundle_ids"]), ("surgeon", ["B02"]))
        self.assertEqual((u["3"]["role_id"], u["3"]["bundle_ids"]), ("gp", ["B03"]))
        self.assertEqual((u["4"]["role_id"], u["4"]["bundle_ids"]), ("emergency_physician", ["B04", "B05"]))
        self.assertEqual((u["5"]["role_id"], u["5"]["bundle_ids"]), ("gp", ["B06"]))

    def test_receptors_only_for_the_surgeon(self):
        for detail in (self.short, self.long):
            self.assertNotIn("receptors_ki67", {c["slot"] for c in detail["1"]["cards"]})
        self.assertIn("receptors_ki67", {c["slot"] for c in self.short["2"]["cards"]})

    def test_b04_implies_b05(self):
        self.assertIn("B05", expand(self.k, ["B04"]))
        self.assertEqual(self.long["4"]["understood"]["implied"], ["B05"])
        p = {s["slot"]: s["priority"] for s in self.long["4"]["understood"]["slots"]}
        self.assertEqual(p["kidney_function"], "P1")  # from B05 P1, never asked for directly

    def test_role_modifiers(self):
        p = {s["slot"]: s for s in self.long["1"]["understood"]["slots"]}
        self.assertEqual(p["airway"]["priority"], "P1")  # B01 P2 -> anaesthetist modifier P1
        self.assertTrue(any(o.startswith("role anaesthetist") for o in p["airway"]["origins"]))

    def test_short_mode_size(self):
        for sid in SITUATIONS:
            n_short, n_long = len(self.short[sid]["cards"]), len(self.long[sid]["cards"])
            self.assertTrue(0 < n_short <= SHORT_MAX, "situation %s: %d short cards" % (sid, n_short))
            self.assertGreaterEqual(n_long, n_short)
            self.assertTrue(all(c["priority"] == "P1" for c in self.short[sid]["cards"]))
            self.assertLessEqual({c["slot"] for c in self.short[sid]["cards"]},
                                 {c["slot"] for c in self.long[sid]["cards"]})

    def test_card_fields(self):
        for sid, s in self.long.items():
            for c in s["cards"]:
                with self.subTest(sid=sid, slot=c["slot"]):
                    self.assertEqual(c["slot"], c["need"])
                    self.assertTrue(c["label_en"] and c["shape"] and c["why"])
                    self.assertIn(c["priority"], ("P1", "P2", "P3"))
                    self.assertIn(c["status"], ("consistent", "conflicting", "outdated", "not_documented"))
                    self.assertTrue(all(src["id"] in self.k.guideline_by_id or src["id"] in self.k.label_by_id
                                        for src in c["sources"]))
                    if c["status"] != "not_documented":
                        self.assertTrue(c["facts"] and c["passages"])
                    else:
                        self.assertTrue(c.get("searched") or c.get("open_checks") is not None)
            self.assertTrue(any(c["sources"] for c in s["cards"]))

    def test_age_from_date_of_birth(self):
        st = store()
        card = next(c for c in self.long["1"]["cards"] if c["slot"] == "age_sex")
        dob = next(_dob(f["attrs"]["value"]) for f in st.facts if f["category"] == "date_of_birth")
        self.assertEqual(card["calculated"]["age"], age_years(dob, _d(st.anchor_date())))

    def test_status_vocabulary(self):
        card = next(c for c in self.long["3"]["cards"] if c["slot"] == "diagnoses_all")
        st = store()
        for it in card["items"]:
            a = (st.fact_by_id[it["facts"][-1]].get("attrs") or {}).get("assertion")
            if a == "negative":
                self.assertEqual(it.get("status_display"), "ruled out")

    def test_followup_status_check(self):
        card = next(c for c in self.long["5"]["cards"] if c["slot"] == "followup_done")
        self.assertTrue(card["checklist"])
        for row in card["checklist"]:
            self.assertIn(row["status"], ("found", "not_documented"))
            self.assertTrue(row["passages"], row)  # evidence, or the recommendation it was checked against
        self.assertTrue(any(r["status"] == "not_documented" for r in card["checklist"]))

    def test_rules_fire_on_facts(self):
        self.assertIn("R03", self.long["4"]["understood"]["rules"]["fired"])  # metformin before contrast
        self.assertIn("R14", self.long["3"]["understood"]["rules"]["fired"])  # two or more dated weights
        self.assertIn("R01", self.long["1"]["understood"]["rules"]["fired"])  # antithrombotic before procedure
        p = {s["slot"]: s["priority"] for s in self.long["1"]["understood"]["slots"]}
        self.assertEqual(p["coagulation"], "P1")  # R01 is a safety rule: adds at P1

    def test_label_panel_never_a_verdict(self):
        cards = [c for c in self.long["4"]["cards"] if c.get("label_panel")]
        self.assertTrue(cards)
        for c in cards:
            for panel in c["label_panel"]:
                self.assertTrue(panel["labels"])
                for row in panel["listed_contraindications"]:
                    for r in row["related"]:
                        self.assertIn(r["status"], ("found", "documented_none", "not_documented"))
                self.assertNotIn("contraindicated for", json.dumps(panel).lower())


class TestUnseenRoles(unittest.TestCase):
    def test_eight_roles_from_the_kb(self):
        k = kbmod.kb()
        tests = {re.sub(r"\s*\(.*\)", "", t["role"]).lower(): t for t in k.data["validation"]["extra_tests"]}
        for role_id, name in UNSEEN_ROLES.items():
            t = tests[name.lower()]
            text = "You are the %s. %s." % (name.lower(), t["situation"])
            with self.subTest(role=role_id):
                s, sh = screen(text), screen(text, "short")
                u = s["understood"]
                self.assertEqual(u["role_id"], role_id, text)
                self.assertNotEqual(u["bundle_ids"], [k.fallback_bundle], text)
                for b in re.findall(r"B\d\d", t["expected"]):
                    self.assertIn(b, u["bundle_ids"], text)
                self.assertTrue(sh["cards"] and len(sh["cards"]) <= SHORT_MAX, text)
                self.assertTrue(any(c["status"] != "not_documented" for c in s["cards"]), text)
                self.assertLess(s["timing_ms"], 1000)

    def test_kb_hold_out_routing(self):
        """The KB's 22 hold-out situations: report agreement; known mismatches are KB review items."""
        k = kbmod.kb()
        good, misses = 0, []
        for t in k.data["validation"]["extra_tests"]:
            role = re.sub(r"\s*\(.*\)", "", t["role"])
            u = screen("You are the %s. %s." % (role, t["situation"]), "short")["understood"]
            exp = re.findall(r"B\d\d", t["expected"])
            ok = set(exp) <= set(u["bundle_ids"]) and ("B18" not in exp or u["bundle_ids"] == ["B18"])
            good += ok
            if not ok:
                misses.append((t["role"], t["situation"], u["bundle_ids"], t["expected"]))
        self.assertGreaterEqual(good, 20, misses)

    def test_fallback_is_visible(self):
        s = screen("Chest pain at night. You are the emergency physician.")
        self.assertEqual(s["understood"]["bundle_ids"], ["B18"])
        self.assertTrue(s["understood"]["fallback_note"])
        s = screen("Something completely different.")  # no role, no task: clinical gate (test_clinical_gate)
        self.assertEqual(s["understood"]["role_id"], "other")
        self.assertEqual(s["screen_mode"], "not_authorised")
        self.assertIn("clinical role", s["understood"]["fallback_note"])

    def test_german_and_fuzzy(self):
        u = screen("Anästhesist: Prämedikationsvisite vor Quadrantektomie")["understood"]
        self.assertEqual((u["role_id"], u["bundle_ids"]), ("anaesthetist", ["B01"]))
        u = screen("anesthesiologst here, pre-op visit")["understood"]
        self.assertEqual(u["role_id"], "anaesthetist")

    def test_legacy_flag(self):
        s = build_screen(SITUATIONS["1"], use_llm=False, rulebook="legacy")
        self.assertNotEqual(s.get("rulebook"), "kb")
        self.assertTrue(s["safety_strip"])


if __name__ == "__main__":
    unittest.main()
