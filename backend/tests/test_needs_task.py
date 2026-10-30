"""'No task, no data' (docs/DECISIONS.md 19) through the real /briefing endpoint: a greeting, a role alone or a
role + greeting returns the needs_task screen with nothing from the record (no facts, counts, dates, titles)."""
import json

import pytest

pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from app import adapter  # noqa: E402


@pytest.fixture(scope="module")
def client():
    mp = pytest.MonkeyPatch()
    mp.setenv("SECOND_LOOK_AUTH", "0")
    mp.delenv("SECOND_LOOK_LLM", raising=False)
    from app import main
    with TestClient(main.app) as c:
        yield c
    mp.undo()


def record_strings(client):
    """Patient-identifying strings of the open record: document titles, dates, date of birth, sex words."""
    out = set()
    for d in client.get("/documents").json():
        out.update(x for x in (d.get("title"), d.get("date"), d.get("department")) if x)
    st = adapter.engine_store()
    for f in st.facts:
        if f.get("category") in ("date_of_birth", "age", "sex", "case_number"):
            v = (f.get("attrs") or {}).get("value")
            if v and len(str(v)) >= 4:
                out.add(str(v))
    out.update(["Patientin", "weiblich", "female", "years old", "Jahre"])
    return out


@pytest.mark.parametrize("text,mode", [("hi", "needs_task"), ("Anaesthetist, hi", "needs_task"),
                                       ("Anaesthetist", "needs_task")])
def test_no_task_no_patient_data(client, text, mode):
    r = client.post("/briefing", json={"situation": text})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["routing"]["screen_mode"] == mode
    assert b["needs"] == [] and b["findings"] == [] and b["blind_spot"] == []
    assert b["stats"]["facts_shown"] == 0 and b["stats"]["facts_dropped"] == 0
    assert all(v == 0 for k, v in b["stats"].items() if k != "engine_ms")
    assert b["as_of"] == "" and b["routing"]["anchor_date"] is None
    assert b["routing"]["message"] and b["routing"]["suggestions"]
    if mode == "needs_task":
        assert "describe your task" in b["routing"]["message"]
    dump = json.dumps(b, ensure_ascii=False)
    leaked = [s for s in record_strings(client) if s in dump]
    assert leaked == []


def test_vague_clinical_request_still_gets_data(client):
    b = client.post("/briefing", json={"situation": "Anaesthetist, patient is coming in tomorrow, anything I "
                                                    "should worry about?"}).json()
    assert b["routing"]["screen_mode"] not in ("needs_task", "not_authorised")
    assert b["stats"]["facts_shown"] > 0


@pytest.mark.parametrize("text", ["STAT CT head, any bleeding risk meds?", "medication review and diabetes check"])
def test_clear_task_without_role_asks_who_is_asking(client, text):
    b = client.post("/briefing", json={"situation": text}).json()
    assert b["routing"]["screen_mode"] == "needs_task" and b["routing"]["role_missing"] is True
    assert b["needs"] == [] and b["findings"] == [] and b["stats"]["facts_shown"] == 0
    assert "Please say who you are" in b["routing"]["message"]
    leaked = [s for s in record_strings(client) if s in json.dumps(b, ensure_ascii=False)]
    assert leaked == []
