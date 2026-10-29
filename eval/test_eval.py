"""Unit tests for the eval harness on the synthetic fixture.

    python3 -m unittest eval.test_eval -v
"""
import copy
import json
import os
import tempfile
import unittest

from eval import core
from eval.fixtures import make_fixture as mf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        mf.write(self.tmp)
        self.raw = os.path.join(self.tmp, "raw")
        self.keys = core.load_json(os.path.join(self.tmp, "answer_keys.json"))
        docs, passages, facts = mf.build()
        self.docs, self.passages, self.facts = docs, passages, facts

    def b(self):
        return core.Build(copy.deepcopy(self.docs), copy.deepcopy(self.passages),
                          copy.deepcopy(self.facts))

    def fact(self, build, fid):
        return build.fact_by_id[fid]

    def codes(self, build):
        return [c for c, _m in core.check_invariants(build, self.raw)["violations"]]

    def cov(self, build):
        return {q["id"]: q for q in core.check_coverage(build, self.keys)}


class TestInvariants(Fixture):
    def test_clean_fixture(self):
        r = core.check_invariants(self.b(), self.raw)
        self.assertEqual(r["violations"], [])
        self.assertEqual(r["warnings"], [])

    def test_display_text_derivation(self):
        b = self.b()
        b.docs["90000002"]["display_text"] = b.docs["90000002"]["display_text"].replace(">", "&gt;")
        self.assertIn("a0", self.codes(b))

    def test_bad_offsets(self):
        b = self.b()
        b.passages[3]["start"] += 1
        self.assertIn("a", self.codes(b))

    def test_quote_not_in_passage(self):
        b = self.b()
        self.fact(b, "f02")["quote"] = "Ramipril 5 mg oral"
        self.assertIn("b", self.codes(b))

    def test_quote_whitespace_only_difference_allowed_for_passage(self):
        b = self.b()
        # passage text with doubled space, quote single-spaced: matches after ws-normalisation,
        # but stored quote must still be exact in display_text -> a 'b' violation
        self.fact(b, "f02")["quote"] = "Ramipril  5mg oral"
        codes = self.codes(b)
        self.assertIn("b", codes)

    def test_invented_number(self):
        b = self.b()
        self.fact(b, "f02")["label_en"] = "Ramipril 10 mg 1-0-0"
        self.assertEqual(self.codes(b), ["c"])

    def test_typo_date_copied_verbatim(self):
        b = self.b()
        f = self.fact(b, "f11")
        f["quote"] = "Aufnahme am 03/01/2020 | Entlassen am 09/01/2020"
        f["label_en"] = "Admitted 03/01/2020, discharged 09/01/20207 (as written)"
        r = core.check_invariants(b, self.raw)
        self.assertIn("c", [c for c, _ in r["violations"]])  # 20207 not in quote
        b.docs["90000001"]["display_text"] = b.docs["90000001"]["display_text"].replace(
            "09/01/2020", "09/01/20207")
        for p in b.passages:
            if p["id"] == f["passage_ids"][0]:
                p["text"] = p["text"].replace("09/01/2020", "09/01/20207")
        f["quote"] = "Aufnahme am 03/01/2020 | Entlassen am 09/01/20207"
        self.assertEqual([c for c, _ in core.check_invariants(b)["violations"] if c == "c"], [])

    def test_number_in_attrs(self):
        b = self.b()
        self.fact(b, "f02")["attrs"]["dose"] = "7.5 mg"
        self.assertEqual(self.codes(b), ["c"])

    def test_decimal_comma_and_roman(self):
        b = self.b()
        self.fact(b, "f03")["label_en"] = "Metoprolol 47.5 mg 1-0-1/2, grade II"
        self.assertEqual(self.codes(b), [])

    def test_declared_calculated_values(self):
        b = self.b()
        f = self.fact(b, "f08")
        f["label_en"] = "Weight 85 kg (-5 kg)"
        f["attrs"] = {"value": 85, "calculated": {"delta_kg": -5}}
        r = core.check_invariants(b, self.raw)
        self.assertEqual(r["violations"], [])

    def test_date_number_is_warning(self):
        b = self.b()
        self.fact(b, "f09")["label_en"] = "LVEF 55% (03/2020)"
        r = core.check_invariants(b, self.raw)
        self.assertEqual(r["violations"], [])
        self.assertTrue(any(c == "c-date" for c, _ in r["warnings"]))

    def test_json_only_age(self):
        b = self.b()
        f = copy.deepcopy(self.fact(b, "f01"))
        f.update(id="f99", category="age", label_en="Age 44 years")
        b.facts.append(f)
        b.fact_by_id["f99"] = f
        self.assertIn("d", self.codes(b))

    def test_json_only_admission_date(self):
        b = self.b()
        self.fact(b, "f11")["date"] = "2020-01-04"
        self.assertIn("d", self.codes(b))

    def test_cave_generic_drug_allergy(self):
        b = self.b()
        self.fact(b, "f01")["label_en"] = "Drug allergy"
        self.assertIn("d", self.codes(b))

    def test_missing_passage(self):
        b = self.b()
        self.fact(b, "f01")["passage_ids"] = ["90000001:p9999"]
        self.assertIn("e", self.codes(b))
        self.fact(b, "f01")["passage_ids"] = []
        self.assertIn("e", self.codes(b))


class TestCoverage(Fixture):
    def test_all_pass(self):
        self.assertTrue(all(q["pass"] for q in self.cov(self.b()).values()))

    def test_half_dose_does_not_match_full(self):
        keys = copy.deepcopy(self.keys)
        keys["F2"]["sources"] = ["90000001"]  # only has 1-0-1/2
        self.keys = keys
        q = self.cov(self.b())["F2"]
        self.assertFalse(q["pass"])
        self.assertEqual(q["items"][0]["missing"], [["1-0-1", "1 0 1 0"]])
        self.assertEqual(q["items"][0]["nearest"][0]["id"], "f04")  # full match, wrong doc

    def test_source_restriction(self):
        b = self.b()
        self.fact(b, "f01")["passage_ids"] = [p["id"] for p in b.passages
                                              if p["doc_id"] == "90000002"][:1]
        self.assertFalse(self.cov(b)["F1"]["pass"])

    def test_item_sources_override(self):
        b = self.b()
        # move weight 90 to doc 2 -> F3 item '90 kg' (sources 90000001) must fail
        self.fact(b, "f06")["passage_ids"] = ["90000002:p0002"]
        self.assertFalse(self.cov(b)["F3"]["pass"])

    def test_union_scope(self):
        keys = copy.deepcopy(self.keys)
        keys["F1"]["items"][0]["scope"] = "union"
        keys["F1"]["items"][0]["groups"] = [["penicillin", "ramipril"], ["exanthem"], ["5 mg"]]
        self.keys = keys
        self.assertTrue(self.cov(self.b())["F1"]["pass"])

    def test_not_documented_forbid(self):
        b = self.b()
        f = copy.deepcopy(self.fact(b, "f10"))
        f.update(id="f98", label_en="Lab check done", status="historical", date="2020-02-01")
        b.facts.append(f)
        self.assertFalse(self.cov(b)["F4"]["pass"])
        f["status"] = "recommended"
        self.assertTrue(self.cov(b)["F4"]["pass"])
        f["status"] = "historical"
        f["date"] = "2020-01"  # month precision: not definitely after 2020-01-09
        self.assertTrue(self.cov(b)["F4"]["pass"])

    def test_passage_hint(self):
        b = self.b()
        b.facts = [f for f in b.facts if f["id"] != "f01"]
        it = self.cov(b)["F1"]["items"][0]
        self.assertFalse(it["pass"])
        self.assertEqual(it["passage_hints"][0]["linked_facts"], [])


class TestContradictions(Fixture):
    def test_bmi_check(self):
        r = core.check_contradictions(self.b(), bmi_docs=(("90000001", False),))
        c = r["checks"][1]
        self.assertTrue(c["ready"])
        self.assertIn("CONTRADICTION", c["detail"])

    def test_overweight_is_not_weight(self):
        self.assertIsNone(core._measure_kind({"category": "diagnosis", "label_en": "Overweight"}))
        self.assertEqual(core._measure_kind({"category": "weight", "label_en": "x"}), "weight")

    def test_side(self):
        self.assertEqual(core.fact_side({"quote": "Stenose der A. carotis interna links."}), "left")
        self.assertEqual(core.fact_side({"quote": "Rechts findet sich eine Stenose"}), "right")
        self.assertEqual(core.fact_side({"attrs": {"side": "L"}}), "left")


class TestHelpers(unittest.TestCase):
    def test_norm(self):
        self.assertEqual(core.norm("Glucophage 1000mg"), core.norm("glucophage 1000 mg"))
        self.assertEqual(core.norm("HbA1c 6,4 %"), "hba1c 6.4%")
        self.assertEqual(core.norm("Byetta 5µg"), core.norm("byetta 5 μg"))

    def test_boundaries(self):
        f = {"date": "2016-04-15"}
        t = core.norm("Testolol 8mg p.o. 1 0 1/2 0")
        self.assertFalse(core.alt_matches("1 0 1", f, t))
        self.assertFalse(core.alt_matches("1-0-1", f, t))
        self.assertTrue(core.alt_matches("1-0-1", f, core.norm("Testolol 8mg p.o. 1 0 1 0")))
        self.assertFalse(core.alt_matches("ass", f, core.norm("Klasse")))
        self.assertTrue(core.alt_matches("quadrant", f, "quadrantenresektion"))
        self.assertTrue(core.alt_matches("@date:2016-04", f, ""))
        self.assertFalse(core.alt_matches("6", f, "60%"))

    def test_dates(self):
        self.assertEqual(core.dates_in_text("am 03. April 2016 und 12/04/2016"),
                         {"2016-04-03", "2016-04-12"})
        self.assertTrue(core.date_after("2016-04-xx", "2015-06-14"))
        self.assertFalse(core.date_after("2015-06-xx", "2015-06-14"))
        self.assertTrue(core.date_after("2015-06-28", "2015-06-14"))
        self.assertFalse(core.date_after(None, "2015-06-14"))

    def test_numbers(self):
        self.assertIn("6.4", core.numbers_in("HbA1c von 6,4%"))
        self.assertIn("2", core.numbers_in("Typ II"))
        self.assertEqual(sorted(core.numbers_to_check("16.05.2016")), ["16", "2016", "5"])
        self.assertEqual(core.numbers_to_check("LVEF 60% (June 2015)", True),
                         [("2015", True), ("60", False)])
        self.assertEqual(core.numbers_to_check("seen 06/2015, 2016-04", True),
                         [("2016", True), ("4", True), ("6", True), ("2015", True)])


class TestRealKeys(unittest.TestCase):
    def test_keys_match_expected(self):
        keys = core.load_json(os.path.join(ROOT, "eval", "answer_keys.json"))
        with open(os.path.join(ROOT, "cases", "expected.json"), encoding="utf-8") as fh:
            exp = {q["id"]: q for q in json.load(fh)}
        self.assertEqual(sorted(k for k in keys if not k.startswith("_")), sorted(exp))
        for qid, q in exp.items():
            self.assertEqual(sorted(keys[qid]["sources"]), sorted(q["sources"]), qid)
            for it in keys[qid]["items"]:
                self.assertTrue(it["groups"] and all(it["groups"]), (qid, it["name"]))


if __name__ == "__main__":
    unittest.main()
