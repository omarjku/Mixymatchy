"""Statistics worth displaying (engine/stats.py, docs/DECISIONS.md 23): daily dose change, recorded vs
calculated BMI per letter, blood pressure day vs night; every result links all its input passages; HbA1c,
EF and height stay dated facts.

    python3 -m unittest engine.test_stats
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import stats as S  # noqa: E402
from engine.screen import build_screen  # noqa: E402

HAS_DATA = os.path.exists(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       "data", "build", "facts.json"))
ED = ("Emergency department at night. You are the emergency physician on night duty. She arrives at 02:00 with "
      "dizziness and blurred vision in the left eye.")
GP = "Diabetes review at the GP. You are her general practitioner (GP), reviewing her diabetes in spring 2016."
CARDIO = "Cardiologist: hypertension review"


def screen(text, as_of=None):
    return build_screen(text, as_of=as_of, use_llm=False, detail="short", rulebook="kb")


def card(s, slot):
    return next(c for c in s["cards"] + (s.get("also_relevant") or []) if c["slot"] == slot)


def stat_lines(c, kind):
    return [x for x in c.get("computed_lines") or [] if x.get("stat") == kind]


class Parse(unittest.TestCase):
    def test_schedules(self):
        self.assertEqual(S.schedule_total("1-0-1/2"), 1.5)
        self.assertEqual(S.schedule_total("1 0 1/2 0"), 1.5)
        self.assertEqual(S.schedule_total("1-1-1"), 3)
        self.assertEqual(S.schedule_total("0-1-0"), 1)
        self.assertEqual(S.schedule_total("2-0-2"), 4)
        self.assertIsNone(S.schedule_total("bei Bedarf"))
        self.assertIsNone(S.schedule_total(""))

    def test_daily_total(self):
        f = {"attrs": {"dose": "16 mg", "schedule": "1-0-1/2"}}
        self.assertEqual(S.daily_total(f)[:2], (24.0, "mg"))
        self.assertIsNone(S.daily_total({"attrs": {"dose": "2 puffs", "schedule": "1-0-0"}}))


@unittest.skipUnless(HAS_DATA, "needs data/build (python3 -m pipeline.build)")
class Screens(unittest.TestCase):
    def test_dose_change_on_the_drug_card_and_key_facts(self):
        s = screen(ED)
        line = stat_lines(card(s, "med_antihypertensive"), "daily_dose_change")
        self.assertEqual(len(line), 1)
        self.assertEqual(line[0]["value"], "24 → 32 mg/day: +8 mg/day (+33%)")
        self.assertEqual(len(line[0]["passages"]), 2)  # both lists linked
        kf = [c for ln in s["key_facts"] for c in ln["computed"] if c["label"] == "Candesartan daily dose"]
        self.assertEqual(len(kf), 1)
        self.assertLessEqual(len(s["key_facts"]), 8)

    def test_dose_change_once_per_screen(self):
        s = screen("Pharmacist reviewing her medications")
        kf = [c for ln in s["key_facts"] for c in ln["computed"] if c["label"] == "Candesartan daily dose"]
        self.assertEqual(len(kf), 1)

    def test_dose_change_needs_two_lists_by_the_as_of_date(self):
        s = screen(ED, as_of="2016-04-06")
        self.assertEqual(stat_lines(card(s, "med_antihypertensive"), "daily_dose_change"), [])

    def test_bmi_recorded_vs_calculated(self):
        s = screen(GP)
        lines = stat_lines(card(s, "weight"), "bmi_check")
        self.assertEqual([x["value"].split(":")[0] for x in lines],
                         ["recorded 29.4, calculated 26.99 from 78 kg and 170 cm",
                          "recorded 29, calculated 22.91 from 67 kg and 171 cm",
                          "recorded 22.8, calculated 22.84 from 66 kg and 170 cm"])
        self.assertEqual([x["consistent"] for x in lines], [False, False, True])
        self.assertTrue(all(len(x["passages"]) == 3 for x in lines))  # height, weight and BMI linked
        self.assertEqual([x.get("key", False) for x in lines], [False, False, True])  # newest letter in key facts
        self.assertIn("-15.4%", card(s, "weight")["value_en"])  # 78 -> 66 kg: -12 kg, -15.4%

    def test_bp_day_night_not_pooled(self):
        s = screen(CARDIO)
        lines = stat_lines(card(s, "vitals_bp_hr"), "bp_day_night")
        self.assertEqual(len(lines), 1)
        self.assertIn("day 140/88, night 128/80 mmHg: night -12/-8 mmHg", lines[0]["value"])
        self.assertEqual(len(lines[0]["passages"]), 2)

    def test_sparse_values_stay_dated_facts(self):
        s = screen(GP)
        self.assertIsNone(card(s, "hba1c").get("calculated"))
        s = screen("Cardiologist: hypertension review")
        self.assertIsNone(card(s, "lvef").get("calculated"))
        s = screen("Nurse, admission: height and weight")
        hb = [c for c in s["cards"] if c["slot"] == "height_bmi"]
        if hb:
            self.assertIsNone(hb[0].get("calculated"))
            self.assertNotIn("change", hb[0]["value_en"].lower())


if __name__ == "__main__":
    unittest.main()
