"""Tests for the access-security module.  Run:  python3 -m unittest security.test_security -v"""

from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from security import auth
from security.auth import AuditLog, AuthError, AuthService, User, hash_secret, verify_secret

PASSWORD = "correct-horse-battery"
PIN = "4826"
DEMO_PASSWORD = "SecondLook-demo-2026"   # documented in security/README.md
DEMO_PIN = "2468"


class FakeClock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


_USER = None


def make_user() -> User:
    global _USER
    if _USER is None:  # hashing is deliberately slow; do it once
        _USER = User("nurse.test", "Nurse Test", "nurse", hash_secret(PASSWORD), hash_secret(PIN))
    return _USER


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.audit_path = Path(self.tmp.name) / "audit" / "audit.jsonl"
        self.clock = FakeClock()
        self.svc = AuthService({"nurse.test": make_user()}, AuditLog(self.audit_path), clock=self.clock)

    def tearDown(self):
        self.tmp.cleanup()

    def events(self):
        return [e["event"] for e in self.svc.audit.entries()]


class HashingTests(unittest.TestCase):
    def test_roundtrip_and_format(self):
        h = hash_secret("s3cret-value")
        scheme, iterations, salt, digest = h.split("$")
        self.assertEqual(scheme, "pbkdf2_sha256")
        self.assertGreaterEqual(int(iterations), 200_000)
        self.assertTrue(verify_secret("s3cret-value", h))
        self.assertFalse(verify_secret("s3cret-valuf", h))
        self.assertNotIn("s3cret-value", h)

    def test_salted(self):
        self.assertNotEqual(hash_secret("1234"), hash_secret("1234"))

    def test_rejects_weak_or_malformed(self):
        with self.assertRaises(ValueError):
            hash_secret("x", iterations=1000)
        self.assertFalse(verify_secret("x", "pbkdf2_sha256$1000$AAAA$AAAA"))
        self.assertFalse(verify_secret("x", "garbage"))
        self.assertFalse(verify_secret("x", None))
        good = hash_secret("abc")
        tampered = good[:-6] + ("A" if good[-6] != "A" else "B") + good[-5:]
        self.assertFalse(verify_secret("abc", tampered))

    def test_pin_format(self):
        self.assertTrue(auth.is_valid_pin("0123"))
        for bad in ("123", "12345", "12a4", "１２３４", 1234, None):
            self.assertFalse(auth.is_valid_pin(bad), bad)

    def test_shipped_users_file(self):
        raw = json.loads(auth.DEFAULT_USERS_FILE.read_text())
        for u in raw["users"]:
            self.assertEqual(set(u), {"staff_id", "display_name", "role", "password_hash", "pin_hash"})
            for key in ("password_hash", "pin_hash"):
                self.assertGreaterEqual(int(u[key].split("$")[1]), 200_000)
        users = auth.load_users()
        demo = users["dr.demo"]
        self.assertTrue(verify_secret(DEMO_PASSWORD, demo.password_hash))
        self.assertTrue(verify_secret(DEMO_PIN, demo.pin_hash))
        self.assertNotIn(DEMO_PASSWORD, auth.DEFAULT_USERS_FILE.read_text())


class LoginAndRateLimitTests(Base):
    def test_login_success(self):
        s = self.svc.login("Nurse.Test ", PASSWORD)
        self.assertGreaterEqual(len(s.token), 40)
        self.assertIs(self.svc.authorize(s.token), s)
        self.assertEqual(self.events(), ["login"])

    def test_wrong_password_and_unknown_user_same_error(self):
        with self.assertRaises(AuthError) as a:
            self.svc.login("nurse.test", "nope-nope-nope")
        with self.assertRaises(AuthError) as b:
            self.svc.login("ghost", "nope-nope-nope")
        self.assertEqual((a.exception.status, a.exception.message), (b.exception.status, b.exception.message))

    def test_lockout_after_five_failures_then_backoff(self):
        for _ in range(5):
            with self.assertRaises(AuthError) as ctx:
                self.svc.login("nurse.test", "wrong-password")
            self.assertEqual(ctx.exception.status, 401)
        # Even the right password is refused during the lockout.
        with self.assertRaises(AuthError) as ctx:
            self.svc.login("nurse.test", PASSWORD)
        self.assertEqual(ctx.exception.status, 429)
        self.assertEqual(ctx.exception.extra["retry_after"], 60)
        self.clock.advance(59)
        with self.assertRaises(AuthError):
            self.svc.login("nurse.test", PASSWORD)
        self.clock.advance(2)
        # Second round of failures doubles the lockout.
        for _ in range(5):
            with self.assertRaises(AuthError):
                self.svc.login("nurse.test", "wrong-password")
        with self.assertRaises(AuthError) as ctx:
            self.svc.login("nurse.test", PASSWORD)
        self.assertEqual(ctx.exception.extra["retry_after"], 120)
        self.clock.advance(121)
        self.assertTrue(self.svc.login("nurse.test", PASSWORD).token)
        self.assertIn("login_blocked", self.events())

    def test_rate_limit_is_per_staff_id(self):
        for _ in range(5):
            with self.assertRaises(AuthError):
                self.svc.login("ghost", "whatever-123")
        self.assertTrue(self.svc.login("nurse.test", PASSWORD).token)


class PinTests(Base):
    def test_wrong_pin_counting_and_reset(self):
        s = self.svc.login("nurse.test", PASSWORD)
        self.svc.lock(s.token)
        for left in (4, 3, 2, 1):
            with self.assertRaises(AuthError) as ctx:
                self.svc.unlock(s.token, "0000")
            self.assertEqual((ctx.exception.status, ctx.exception.extra["attempts_left"]), (403, left))
        self.svc.unlock(s.token, PIN)
        self.assertFalse(s.locked)
        self.assertEqual(s.pin_failures, 0)
        self.svc.authorize(s.token)

    def test_five_wrong_pins_revoke_session(self):
        s = self.svc.login("nurse.test", PASSWORD)
        self.svc.lock(s.token)
        for _ in range(4):
            with self.assertRaises(AuthError):
                self.svc.unlock(s.token, "9999")
        with self.assertRaises(AuthError) as ctx:
            self.svc.unlock(s.token, "abc")  # malformed counts too
        self.assertEqual((ctx.exception.status, ctx.exception.code), (401, "session_revoked"))
        with self.assertRaises(AuthError) as ctx:
            self.svc.unlock(s.token, PIN)  # the right PIN no longer helps
        self.assertEqual(ctx.exception.status, 401)
        self.assertFalse(self.svc.status(s.token)["authenticated"])
        self.assertIn("session_revoked", self.events())

    def test_locked_session_blocks_api(self):
        s = self.svc.login("nurse.test", PASSWORD)
        self.svc.lock(s.token, "manual")
        with self.assertRaises(AuthError) as ctx:
            self.svc.authorize(s.token)
        self.assertEqual(ctx.exception.status, 423)
        self.assertEqual(ctx.exception.extra["attempts_left"], 5)


class IdleAndExpiryTests(Base):
    def test_idle_lock_server_side(self):
        s = self.svc.login("nurse.test", PASSWORD)
        self.clock.advance(179)
        self.svc.authorize(s.token)  # activity resets the timer
        self.clock.advance(179)
        self.svc.authorize(s.token)
        self.clock.advance(180)
        with self.assertRaises(AuthError) as ctx:
            self.svc.authorize(s.token)
        self.assertEqual((ctx.exception.status, ctx.exception.extra["reason"]), (423, "idle"))
        self.assertIn("idle_lock", self.events())
        self.svc.unlock(s.token, PIN)
        self.svc.authorize(s.token)

    def test_status_does_not_count_as_activity(self):
        s = self.svc.login("nurse.test", PASSWORD)
        for _ in range(4):
            self.clock.advance(50)
            self.svc.status(s.token)
        self.assertTrue(self.svc.status(s.token)["locked"])

    def test_max_session_lifetime(self):
        s = self.svc.login("nurse.test", PASSWORD)
        for _ in range(12 * 60 // 2 - 1):  # 11h58m of steady activity
            self.clock.advance(120)
            self.svc.authorize(s.token)
        self.clock.advance(120)
        with self.assertRaises(AuthError) as ctx:
            self.svc.authorize(s.token)
        self.assertEqual((ctx.exception.status, ctx.exception.code), (401, "session_expired"))

    def test_logout_and_unknown_token(self):
        s = self.svc.login("nurse.test", PASSWORD)
        self.assertTrue(self.svc.logout(s.token))
        self.assertFalse(self.svc.logout(s.token))
        for token in (s.token, None, "", "x" * 1000):
            with self.assertRaises(AuthError) as ctx:
                self.svc.authorize(token)
            self.assertEqual(ctx.exception.status, 401)


class AuditTests(Base):
    def test_audit_has_no_secrets(self):
        with self.assertRaises(AuthError):
            self.svc.login("nurse.test", "wrong-password-xyz")
        s = self.svc.login("nurse.test", PASSWORD)
        self.svc.lock(s.token)
        with self.assertRaises(AuthError):
            self.svc.unlock(s.token, "1111")
        self.svc.unlock(s.token, PIN)
        task = "anaesthetist pre-op check for breast surgery"
        self.svc.record_data_access(s, "0000-0001", task)
        self.svc.audit.record("custom", "nurse.test", pin=PIN, password=PASSWORD, token=s.token, note="ok")
        self.svc.logout(s.token)

        text = self.audit_path.read_text()
        for secret in (PASSWORD, "wrong-password-xyz", s.token, task):
            self.assertNotIn(secret, text)
        entries = self.svc.audit.entries()
        for e in entries:
            self.assertTrue(auth.FORBIDDEN_AUDIT_KEYS.isdisjoint(k.lower() for k in e))
            self.assertNotIn(PIN, [v for v in e.values() if isinstance(v, str)])
            self.assertNotIn("1111", [v for v in e.values() if isinstance(v, str)])
            self.assertIn("ts", e)
        events = [e["event"] for e in entries]
        self.assertEqual(events, ["login_failed", "login", "lock", "unlock_failed", "unlock",
                                  "data_access", "custom", "logout"])
        access = entries[5]
        self.assertEqual(access["patient_id"], "0000-0001")
        self.assertEqual(len(access["task_sha256"]), 64)

    def test_hash_chain_detects_tampering(self):
        s = self.svc.login("nurse.test", PASSWORD)
        self.svc.lock(s.token)
        self.svc.logout(s.token)
        self.assertTrue(self.svc.audit.verify_chain())
        lines = self.audit_path.read_text().splitlines()
        del lines[1]
        self.audit_path.write_text("\n".join(lines) + "\n")
        self.assertFalse(AuditLog(self.audit_path).verify_chain())

    def test_tail_newest_first(self):
        for i in range(5):
            self.svc.audit.record("custom", None, n=i)
        self.assertEqual([e["n"] for e in self.svc.audit.tail(3)], [4, 3, 2])


class HttpTests(Base):
    """End-to-end over a real socket."""

    def setUp(self):
        super().setUp()
        from security.server import make_server
        self.server = make_server(self.svc, "127.0.0.1", 0)
        self.server.RequestHandlerClass.log_message = lambda *a: None
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def req(self, method, path, body=None, token=None, headers=None):
        h = {"Content-Type": "application/json", **(headers or {})}
        if token:
            h["Authorization"] = "Bearer " + token
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, json.loads(resp.read() or b"{}"), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}"), e.headers

    def test_full_flow(self):
        code, body, headers = self.req("POST", "/auth/login", {"staff_id": "nurse.test", "password": PASSWORD})
        self.assertEqual(code, 200)
        cookie = headers["Set-Cookie"]
        for flag in ("HttpOnly", "SameSite=Strict", "Path=/"):
            self.assertIn(flag, cookie)
        token = body["token"]
        self.assertEqual(self.req("GET", "/api/ping", token=token)[0], 200)
        self.assertEqual(self.req("GET", "/api/ping")[0], 401)
        self.assertEqual(self.req("POST", "/auth/lock", {}, token=token)[0], 200)
        code, body, _ = self.req("GET", "/api/ping", token=token)
        self.assertEqual((code, body["error"]), (423, "locked"))
        code, body, _ = self.req("POST", "/auth/unlock", {"pin": "0000"}, token=token)
        self.assertEqual((code, body["attempts_left"]), (403, 4))
        self.assertEqual(self.req("POST", "/auth/unlock", {"pin": PIN}, token=token)[0], 200)
        code, body, _ = self.req("GET", "/auth/audit?limit=5", token=token)
        self.assertEqual(code, 200)
        self.assertTrue(body["chain_ok"])
        self.assertEqual(self.req("POST", "/auth/logout", {}, token=token)[0], 200)
        self.assertFalse(self.req("GET", "/auth/status", token=token)[1]["authenticated"])

    def test_cookie_auth_requires_json_content_type(self):
        _, body, _ = self.req("POST", "/auth/login", {"staff_id": "nurse.test", "password": PASSWORD})
        cookie = {"Cookie": "sl_session=" + body["token"]}
        self.assertEqual(self.req("GET", "/api/ping", headers=cookie)[0], 200)
        code, _, _ = self.req("POST", "/auth/lock", None, headers={**cookie, "Content-Type": "text/plain"})
        self.assertEqual(code, 401)

    def test_beacon_logout_with_text_plain_body(self):
        _, body, _ = self.req("POST", "/auth/login", {"staff_id": "nurse.test", "password": PASSWORD})
        token = body["token"]
        r = urllib.request.Request(self.base + "/auth/logout", method="POST",
                                   data=json.dumps({"token": token, "reason": "pagehide"}).encode(),
                                   headers={"Content-Type": "text/plain;charset=UTF-8"})
        with urllib.request.urlopen(r) as resp:
            self.assertEqual(resp.status, 200)
        self.assertEqual(self.req("GET", "/api/ping", token=token)[0], 401)
        self.assertEqual(self.svc.audit.entries()[-1]["reason"], "pagehide")

    def test_rate_limit_http(self):
        for _ in range(5):
            self.req("POST", "/auth/login", {"staff_id": "nurse.test", "password": "bad-password"})
        code, body, headers = self.req("POST", "/auth/login", {"staff_id": "nurse.test", "password": PASSWORD})
        self.assertEqual(code, 429)
        self.assertEqual(headers["Retry-After"], "60")

    def test_static_and_headers(self):
        with urllib.request.urlopen(self.base + "/") as resp:
            self.assertIn("Content-Security-Policy", resp.headers)
            self.assertEqual(resp.headers["X-Frame-Options"], "DENY")
            self.assertIn(b"second-look-lock.js", resp.read())
        with urllib.request.urlopen(self.base + "/second-look-lock.js") as resp:
            self.assertIn(b"SecondLook", resp.read())


class MobileCopyTests(unittest.TestCase):
    def test_mobile_app_bundles_the_current_lock_module(self):
        """mobile/src/second-look/ holds verbatim copies; re-copy after editing security/web/."""
        root = Path(__file__).resolve().parents[1]
        for name in ("second-look-lock.js", "lock.css"):
            copy = root / "mobile" / "src" / "second-look" / name
            if copy.exists():
                self.assertEqual((root / "security" / "web" / name).read_bytes(), copy.read_bytes(), name)


if __name__ == "__main__":
    unittest.main()
