"""Core guarantees. Run from backend/:  python -m pytest -q

Uses small synthetic fixtures (no IBM data needed) except the ingest test, which is skipped without data/.
"""
import pytest

from app.config import PATIENT_DIR
from app.query import build_briefing
from app.schema import Fact, Segment
from app.verify import verify_facts


def seg(sid: str, text: str, date: str) -> Segment:
    return Segment(id=sid, doc_id=sid.split(":")[0], kind="sentence", text=text, start=0, end=len(text), doc_date=date)


OLD, NEW = "2015-06-28", "2016-04-15"
SEGMENTS = [
    seg("D1:s001", "Frau", OLD),
    seg("D1:s002", "Gewicht: 78 kg", OLD),
    seg("D1:s003", "Blopress 16mg oral 1 0 1/2 0 ST", OLD),
    seg("D1:s004", "Nächste geplanter Duplexsonographie der Karotisgefäße in 2 Monaten.", OLD),
    seg("D1:s005", "Schlafapnoe", OLD),
    seg("D2:s001", "Frau", NEW),
    seg("D2:s002", "Gewicht: 66 kg", NEW),
    seg("D2:s003", "Blopress 16mg oral 1 0 1 0 ST", NEW),
    seg("D3:s001", "Gewicht: 60 kg", "2016-09-01"),  # after the as-of date: must be ignored
]


def fact(fid, type_, concept, label, value, sids, classes=()):
    return Fact(id=fid, type=type_, concept=concept, label_en=label, value=value, segment_ids=sids, classes=list(classes))


FACTS = [
    fact("w1", "measurement", "weight", "Weight", "78 kg", ["D1:s002"]),
    fact("w2", "measurement", "weight", "Weight", "66 kg", ["D2:s002"]),
    fact("w3", "measurement", "weight", "Weight", "60 kg", ["D3:s001"]),
    fact("m1", "medication", "drug:candesartan", "Candesartan 16 mg", "1-0-1/2", ["D1:s003"], ["antihypertensive"]),
    fact("m2", "medication", "drug:candesartan", "Candesartan 16 mg", "1-0-1", ["D2:s003"], ["antihypertensive"]),
    fact("r1", "recommendation", "carotid_duplex", "Carotid duplex in 2 months", "2", ["D1:s004"]),
    fact("d1", "diagnosis", "sleep_apnoea", "Sleep apnoea", None, ["D1:s005"]),
]
for f in FACTS:
    f.value = f.value.replace("-", " ") if f.type == "medication" else f.value  # match table layout "1 0 1"


def need(briefing, key):
    return next(n for n in briefing.needs if n.need == key)


# ---------- the safety net ----------

def test_verifier_drops_invented_facts():
    by_id = {s.id: s for s in SEGMENTS}
    fakes = [
        fact("f1", "medication", "drug:candesartan", "Candesartan", "32 mg", ["D2:s003"]),   # wrong dose
        fact("f2", "measurement", "weight", "Weight", "70 kg", ["D2:s002"]),                  # wrong value
        fact("f3", "measurement", "weight", "Weight", "78 kg", ["D2:s002"]),                  # right value, wrong sentence
        fact("f4", "diagnosis", "sle", "Lupus", "SLE", ["D9:s001"]),                          # unknown segment
        fact("f5", "allergy", "penicillin", "Penicillin allergy", "Penicillin", ["D1:s005"]),  # invented text
    ]
    kept, dropped = verify_facts(FACTS[:2] + fakes, by_id)
    assert [f.id for f in kept] == ["w1", "w2"]
    assert len(dropped) == 5


@pytest.mark.skipif(not PATIENT_DIR.exists(), reason="data/ not present")
def test_ingest_offsets_point_at_segment_text():
    from app.ingest import ingest
    docs, segs = ingest()  # ingest() asserts every offset internally
    assert len(docs) == 8 and len(segs) > 300
    assert len({s.id for s in segs}) == len(segs)


# ---------- smart answers ----------

def test_trend_computes_change_and_ignores_values_after_as_of():
    b = build_briefing("GP reviewing her diabetes", FACTS, [], SEGMENTS)
    n = need(b, "weight_trend")
    assert [f.id for f in n.facts] == ["w1", "w2"]
    assert n.computed[0].value == "-12 kg"
    assert set(n.computed[0].segment_ids) == {"D1:s002", "D2:s002"}


def test_newest_medication_list_overrides_older_one():
    b = build_briefing("GP reviewing her diabetes", FACTS, [], SEGMENTS)
    n = need(b, "bp_drugs")
    assert [f.id for f in n.facts] == ["m2"]
    assert [f.id for f in n.superseded] == ["m1"]


def test_followup_without_later_record():
    b = build_briefing("GP checking open follow-ups", FACTS, [], SEGMENTS)
    n = need(b, "followups")
    assert n.computed and n.computed[0].value == f"Nothing recorded after {OLD}"


def test_not_applicable_is_distinct_from_not_documented():
    b = build_briefing("Covering doctor, any prostate findings?", FACTS, [], SEGMENTS)
    n = need(b, "prostate")
    assert n.status == "not_applicable" and n.reason_segment_ids


def test_not_documented_when_absent():
    b = build_briefing("Anaesthetist pre-op check", FACTS, [], SEGMENTS)
    assert need(b, "airway").status == "not_documented"


def test_blind_spot_lists_facts_missing_from_latest_letter():
    b = build_briefing("Anaesthetist pre-op check", FACTS, [], SEGMENTS)
    assert "sleep_apnoea" in {f.concept for f in b.blind_spot}
    assert "weight" not in {f.concept for f in b.blind_spot}


def test_stats_are_computed_from_the_screen():
    b = build_briefing("Anaesthetist pre-op check", FACTS, [], SEGMENTS)
    assert b.stats["facts_shown"] == sum(len(n.facts) for n in b.needs)
    assert b.stats["blind_spot"] == len(b.blind_spot)
