"""Engine -> schema adapter.  From backend/:  python -m pytest -q tests/test_adapter.py

For the 5 case situations (title + description only, never the questions):
  * the Briefing validates against schema.py (round trip through JSON)
  * every fact (shown, superseded, blind spot) and every finding/computed value links to segments that exist
  * stats are counted from the briefing itself
  * the 15 expected answers are on screen: the token logic of eval/answer_keys.json (eval.core) applied
    only to what the briefing contains (label, value, unit, side, status, date of each Fact), linked to a
    source document through its segment ids
  * each briefing builds in under 1 second
Skipped when data/build/ cannot be built (no patient data).
"""
import json
import time

import pytest

from app import adapter
from app.schema import Briefing

ROOT = adapter.ROOT
pytest.importorskip("engine")
if not (ROOT / "data" / "build" / "facts.json").exists() and not (adapter.RAW_DIR / "documents").exists():
    pytest.skip("no patient data", allow_module_level=True)

from engine.test_engine import SITUATIONS  # noqa: E402  (the 5 case situations, shared with the engine tests)
from eval.core import Build, eval_question, norm  # noqa: E402


@pytest.fixture(scope="module")
def briefings():
    out = {}
    for sid, text in SITUATIONS.items():
        t0 = time.perf_counter()
        b = adapter.build_briefing(text, use_llm=False)
        out[sid] = (b, time.perf_counter() - t0)
    return out


def all_facts(b: Briefing):
    return [f for n in b.needs for f in n.facts + n.superseded] + list(b.blind_spot)


def test_schema_round_trip(briefings):
    for sid, (b, secs) in briefings.items():
        again = Briefing.model_validate(json.loads(b.model_dump_json()))
        assert again == b, sid
        assert secs < 1.0, "situation %s took %.2fs" % (sid, secs)
        assert b.needs and b.role != "fallback"


def test_every_link_exists(briefings):
    known = adapter.segment_index()
    for sid, (b, _) in briefings.items():
        for f in all_facts(b):
            assert f.segment_ids, (sid, f.id)
            assert all(s in known for s in f.segment_ids), (sid, f.id, f.segment_ids)
        for n in b.needs:
            for c in n.computed:
                assert c.segment_ids and all(s in known for s in c.segment_ids), (sid, n.need, c)
            assert all(s in known for s in n.reason_segment_ids), (sid, n.need)
            if n.status == "documented":
                assert n.facts, (sid, n.need)
        for f in b.findings:
            assert f.segment_ids and all(s in known for s in f.segment_ids), (sid, f.id)


def test_segments_are_slices_of_documents():
    docs = {d.id: d for d in adapter.documents()}
    assert len(docs) == 8
    for s in adapter.segments():
        assert docs[s.doc_id].text[s.start:s.end] == s.text, s.id
        assert s.doc_date == docs[s.doc_id].date


def test_stats_counted_from_briefing(briefings):
    for sid, (b, _) in briefings.items():
        s = b.stats
        shown = [f for n in b.needs for f in n.facts]
        assert s["facts_shown"] == len(shown) > 0
        assert s["facts_verified"] == s["facts_shown"]
        assert s["computed_values"] == sum(len(n.computed) for n in b.needs)
        assert s["not_documented"] == sum(n.status == "not_documented" for n in b.needs)
        assert s["not_applicable"] == sum(n.status == "not_applicable" for n in b.needs)
        assert s["blind_spot"] == len(b.blind_spot)
        assert s["contradictions"] == sum(f.tier == "contradiction" for f in b.findings)
        assert s["documentation_notes"] == sum(f.tier == "documentation_note" for f in b.findings)
        assert s["contradictions"] == 5 and s["documentation_notes"] == 3


def _fact_dict(f):
    attrs = {"value": f.value, "unit": f.unit, "side": f.side, "status": f.status}
    return {"id": f.id, "label_en": f.label_en, "attrs": attrs, "date": f.date, "status": f.status,
            "passage_ids": f.segment_ids}


def test_15_answers_on_screen(briefings):
    keys = json.loads((ROOT / "eval" / "answer_keys.json").read_text(encoding="utf-8"))
    st = adapter.engine_store()
    failures = []
    for qid in sorted(k for k in keys if not k.startswith("_")):
        b, _ = briefings[qid.split(".")[0]]
        facts = list({f.id: _fact_dict(f) for f in all_facts(b)}.values())
        build = Build(st.docs, st.passages, facts)
        texts = {f["id"]: norm(f["label_en"] + " | " + " ".join(str(v) for v in f["attrs"].values() if v))
                 for f in facts}
        res = eval_question(build, qid, keys[qid], texts)
        if not res["pass"]:
            failures.append((qid, [(i["name"], i["missing"]) for i in res["items"] if not i["pass"]],
                             res["forbidden_hits"]))
    assert failures == [], failures


def test_superseded_and_computed(briefings):
    def need(sid, key):
        return next(n for n in briefings[sid][0].needs if n.need == key)

    bp = need("4", "antihypertensives")
    assert [f.label_en for f in bp.facts] == ["Candesartan (Blopress) 16 mg 1-0-1"]
    assert any("1-0-1/2" in f.label_en and f.date.startswith("2015") for f in bp.superseded)
    w = need("3", "weight_change")
    assert w.computed and w.computed[0].value.startswith("-12 kg")
    assert need("1", "lvef").facts[0].trust == "stale"
    assert all(f.trust == "conflicting" for f in need("1", "carotid").facts)
    duplex = need("5", "carotid_duplex_done")
    assert duplex.status == "not_documented" and duplex.computed  # linked to the recommendation


def test_findings_kinds(briefings):
    b = briefings["5"][0]
    kinds = {f.kind for f in b.findings}
    assert {"conflict", "dropped", "followup"} <= kinds
    assert len(b.blind_spot) == sum(f.kind == "dropped" for f in b.findings)
