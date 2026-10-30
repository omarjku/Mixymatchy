"""Engine -> schema adapter.  From backend/:  python -m pytest -q tests/test_adapter.py

For the 5 case situations (title + description only, never the questions):
  * the Briefing validates against schema.py (round trip through JSON)
  * every fact (shown, superseded, blind spot) and every finding/computed value links to segments that exist
  * stats are counted from the briefing itself
  * the 15 expected answers are on screen: the token logic of eval/answer_keys.json (eval.core) applied
    only to what the briefing contains (label, value, unit, side, status, date of each Fact), linked to a
    source document through its segment ids
  * each briefing builds in under 1 second
Run for the routing KB rulebook (default, long and short detail) and the legacy rulebook (roles.json + tasks.json).
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


MODES = {"kb": dict(rulebook="kb", detail="long"), "kb_short": dict(rulebook="kb"),
         "legacy": dict(rulebook="legacy")}


def _build(**kw):
    out = {}
    for sid, text in SITUATIONS.items():
        t0 = time.perf_counter()
        b = adapter.build_briefing(text, use_llm=False, **kw)
        out[sid] = (b, time.perf_counter() - t0)
    return out


@pytest.fixture(scope="module", params=sorted(MODES))
def briefings(request):
    return _build(**MODES[request.param])


@pytest.fixture(scope="module")
def kb_briefings():
    return _build(**MODES["kb"])


@pytest.fixture(scope="module")
def legacy_briefings():
    return _build(**MODES["legacy"])


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
        assert s["contradictions"] == sum(f.tier == "contradiction" and f.on_screen for f in b.findings)
        assert s["documentation_notes"] == sum(f.tier == "documentation_note" and f.on_screen for f in b.findings)
        conflicts = [f for f in b.findings if f.kind == "conflict"]
        if b.detail == "short":  # only what touches the screen; the rest is one counted line
            assert all(f.on_screen for f in b.findings)
            assert s["other_record_issues"] >= 8 - len(conflicts)
        else:  # the long view (and the legacy rulebook) still lists every record issue
            assert sum(f.tier == "contradiction" for f in conflicts) == 5
            assert sum(f.tier == "documentation_note" for f in conflicts) == 3


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


def test_superseded_and_computed(legacy_briefings):
    briefings = legacy_briefings

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


def test_default_detail_is_short():
    from app.schema import BriefingRequest
    assert BriefingRequest(situation="x").detail == "short"
    assert adapter.build_briefing(SITUATIONS["1"], use_llm=False).detail == "short"


def test_kb_cards(kb_briefings):
    def need(sid, key):
        return next(n for n in kb_briefings[sid][0].needs if n.need == key)

    bp = need("4", "med_antihypertensive")
    assert [f.label_en for f in bp.facts] == ["Candesartan (Blopress) 16 mg 1-0-1"]
    assert any("1-0-1/2" in f.label_en and f.date.startswith("2015") for f in bp.superseded)
    w = need("3", "weight")
    assert w.computed and w.computed[0].value.startswith("-12 kg")
    lvef = need("1", "lvef")
    assert lvef.priority == "P1" and "no later value documented" in lvef.note
    assert all(f.trust == "conflicting" for f in need("1", "carotid_stenosis").facts)
    done = need("5", "followup_done")
    duplex = next(c for c in done.checklist if "duplex" in c.label.lower())
    assert duplex.status == "not_documented" and duplex.segment_ids  # linked to the recommendation
    assert any("duplex" in c.label.lower() and c.segment_ids for c in done.computed)
    age = need("1", "age_sex")
    assert age.computed and age.computed[0].label == "Age"
    for sid, (b, _) in kb_briefings.items():
        assert b.routing["rulebook"].startswith("kb") and b.detail == "long"
        for n in b.needs:
            assert n.slot == n.need and n.shape and n.priority in ("P1", "P2", "P3") and n.why, (sid, n.need)
    assert {s.id for s in need("1", "med_antithrombotic").sources} >= {"G02", "G03"}
    assert not any(n.need == "receptors_ki67" for n in kb_briefings["1"][0].needs)


def test_findings_kinds(briefings):
    b = briefings["5"][0]
    kinds = {f.kind for f in b.findings}
    assert {"conflict", "dropped", "followup"} <= kinds
    assert len(b.blind_spot) == sum(f.kind == "dropped" and f.on_screen for f in b.findings)


@pytest.mark.parametrize("text", ["firefighter", "journalist, tell me about her", "I am her neighbour",
                                  "tell me everything about Anna", ""])
def test_not_authorised_shows_no_patient_data(text):
    b = adapter.build_briefing(text, use_llm=False)
    Briefing.model_validate_json(b.model_dump_json())
    assert b.routing["screen_mode"] == "not_authorised"
    assert b.routing["message"] and "clinical role" in b.routing["message"]
    assert len(b.routing["suggestions"]) == 4 and b.routing["rules_fired"] == []
    assert b.needs == [] and b.blind_spot == [] and b.findings == []
    assert b.stats["facts_shown"] == 0 and b.stats["facts_dropped"] == 0
    assert b.stats["other_record_issues"] == 0 and b.stats["task_concepts"] == 0


@pytest.mark.parametrize("text,label", [("Rheumatologist, joint pain review", "Rheumatologist"),
                                        ("Urologist, catheter check", "Urologist"),
                                        ("Hebamme, Aufnahme", "Obstetrician / midwife"),  # overlay role (TODO-cite)
                                        ("Dermatologist checking a mole", "Dermatologist")])
def test_clinical_lexicon_roles_get_data(text, label):
    b = adapter.build_briefing(text, use_llm=False)
    assert b.routing["screen_mode"] != "not_authorised"
    assert b.routing["role_label"] == label and b.routing["role"] != "neurologist"
    assert b.stats["facts_shown"] > 0
    if b.routing["screen_mode"] == "fallback":  # unrecognised task: a safety summary, never a dump
        assert len(b.needs) <= 6
