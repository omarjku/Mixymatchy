"""Sign-in and PIN lock in front of the patient-data API (app/auth.py), and the SPA fallback (app/main.py)."""
import importlib

import pytest

pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

DEMO = {"staff_id": "dr.demo", "password": "SecondLook-demo-2026"}
PIN = "2468"


@pytest.fixture()
def main(tmp_path, monkeypatch):
    """A fresh app (fresh sessions, temp audit file); STATIC_DIR points at a tiny fake build."""
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=root></div>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    monkeypatch.setenv("STATIC_DIR", str(dist))
    monkeypatch.setenv("SECOND_LOOK_AUDIT", str(tmp_path / "audit.jsonl"))
    monkeypatch.delenv("SECOND_LOOK_USERS", raising=False)
    monkeypatch.delenv("SITE_GATE", raising=False)
    monkeypatch.setenv("SITE_PASSWORD", "legacy")  # as still set on Render: must no longer gate anything
    from app import auth, main as main_mod
    importlib.reload(auth)
    return importlib.reload(main_mod)


@pytest.fixture()
def client(main):
    with TestClient(main.app) as c:
        yield c


def login(client) -> dict:
    r = client.post("/auth/login", json=DEMO)
    assert r.status_code == 200, r.text
    client.cookies.clear()  # exercise the Bearer path the mobile app uses
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_health_is_public(client):
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("method,path", [
    ("get", "/documents"), ("get", "/documents/x"), ("get", "/segments/x"), ("post", "/briefing"),
])
def test_patient_data_needs_sign_in(client, method, path):
    r = getattr(client, method)(path, **({"json": {"situation": "x"}} if method == "post" else {}))
    assert r.status_code == 401
    assert r.json()["error"] == "unauthenticated"


def test_login_unlock_flow_and_audit(client, main):
    h = login(client)
    r = client.post("/briefing", json={"situation": "anaesthetist pre-op check"}, headers=h)
    assert r.status_code == 200
    assert client.get("/documents", headers=h).status_code == 200

    assert client.post("/auth/lock", json={"reason": "manual"}, headers=h).status_code == 200
    r = client.get("/documents", headers=h)
    assert r.status_code == 423 and r.json()["error"] == "locked"
    assert client.post("/auth/unlock", json={"pin": "1111"}, headers=h).status_code == 403
    assert client.post("/auth/unlock", json={"pin": PIN}, headers=h).status_code == 200
    assert client.get("/documents", headers=h).status_code == 200

    audit = client.get("/auth/audit", headers=h).json()
    assert audit["chain_ok"]
    access = [e for e in audit["entries"] if e["event"] == "data_access"]
    assert {e["resource"] for e in access} == {"briefing", "documents"}
    raw = main.auth_service.audit.path.read_text()
    assert "anaesthetist pre-op check" not in raw and PIN not in raw and DEMO["password"] not in raw


def test_five_wrong_pins_revoke_the_session(client):
    h = login(client)
    client.post("/auth/lock", json={}, headers=h)
    for _ in range(4):
        assert client.post("/auth/unlock", json={"pin": "0000"}, headers=h).status_code == 403
    r = client.post("/auth/unlock", json={"pin": "0000"}, headers=h)
    assert r.status_code == 401 and r.json()["error"] == "session_revoked"
    assert client.get("/documents", headers=h).status_code == 401


def test_idle_lock_on_the_server(client, main):
    h = login(client)
    main.auth_service.idle_seconds = 0
    assert client.get("/documents", headers=h).status_code == 423


def test_no_cors_wildcard(client):
    r = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_basic_site_gate_is_off_by_default(client):
    assert client.get("/").status_code == 200
    assert "www-authenticate" not in client.get("/documents").headers


def test_spa_fallback(client):
    assert client.get("/").text.startswith("<!doctype html>")
    assert client.get("/results").text.startswith("<!doctype html>")  # deep link
    assert client.head("/").status_code == 200  # Render health probe
    assert client.get("/hilfe/abc").text.startswith("<!doctype html>")
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/assets/missing.js").status_code == 404
    assert client.get("/documents/nope").status_code == 401  # API paths are not swallowed
    assert client.get("/auth/nope").status_code == 404
    assert client.get("/../security/users.example.json").status_code == 404
