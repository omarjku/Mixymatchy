"""Second Eye access security: hashing, sessions, PIN lock, rate limits, audit.

Framework-agnostic core. ``security/server.py`` exposes it over HTTP, but any
Python backend can import :class:`AuthService` and call ``authorize(token)``
before returning patient data.

Python 3 standard library only.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

# --------------------------------------------------------------------------
# Policy (change here; every value is also overridable per AuthService)
# --------------------------------------------------------------------------
IDLE_LOCK_SECONDS = 3 * 60            # no activity -> session locks (PIN needed)
MAX_SESSION_SECONDS = 12 * 60 * 60    # absolute session lifetime -> full login
MAX_PIN_ATTEMPTS = 5                  # wrong PINs before the session is revoked
LOGIN_MAX_FAILURES = 5                # wrong passwords per staff ID before lockout
LOGIN_LOCKOUT_SECONDS = 60            # first lockout; doubles on each repeat
LOGIN_LOCKOUT_MAX_SECONDS = 15 * 60   # backoff cap
PBKDF2_ITERATIONS = 240_000           # PBKDF2-HMAC-SHA256 work factor for new hashes
MIN_PBKDF2_ITERATIONS = 200_000       # hashes weaker than this are rejected
SALT_BYTES = 16
TOKEN_BYTES = 32                      # secrets.token_urlsafe(32) -> 256-bit token
PIN_LENGTH = 4
MIN_PASSWORD_LENGTH = 10

SECURITY_DIR = Path(__file__).resolve().parent
REPO_ROOT = SECURITY_DIR.parent
DEFAULT_USERS_FILE = Path(os.environ.get("SECOND_LOOK_USERS", SECURITY_DIR / "users.example.json"))
DEFAULT_AUDIT_FILE = Path(os.environ.get("SECOND_LOOK_AUDIT", REPO_ROOT / "data" / "audit" / "audit.jsonl"))

HASH_SCHEME = "pbkdf2_sha256"


# --------------------------------------------------------------------------
# Hashing
# --------------------------------------------------------------------------
def hash_secret(secret: str, *, iterations: int = PBKDF2_ITERATIONS, salt: Optional[bytes] = None) -> str:
    """Return ``pbkdf2_sha256$<iterations>$<salt b64>$<hash b64>`` for a password or PIN."""
    if iterations < MIN_PBKDF2_ITERATIONS:
        raise ValueError(f"iterations must be >= {MIN_PBKDF2_ITERATIONS}")
    if not isinstance(secret, str) or not secret:
        raise ValueError("secret must be a non-empty string")
    salt = salt if salt is not None else secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, iterations)
    return "$".join([HASH_SCHEME, str(iterations),
                     base64.b64encode(salt).decode("ascii"),
                     base64.b64encode(digest).decode("ascii")])


def verify_secret(secret: str, encoded: str) -> bool:
    """Constant-time check of ``secret`` against a :func:`hash_secret` string."""
    try:
        scheme, iterations_s, salt_b64, digest_b64 = encoded.split("$")
        iterations = int(iterations_s)
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(digest_b64, validate=True)
    except (AttributeError, ValueError):
        return False
    if scheme != HASH_SCHEME or iterations < MIN_PBKDF2_ITERATIONS or not isinstance(secret, str):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def is_valid_pin(pin: object) -> bool:
    return isinstance(pin, str) and len(pin) == PIN_LENGTH and pin.isascii() and pin.isdigit()


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class User:
    staff_id: str
    display_name: str
    role: str
    password_hash: str
    pin_hash: str

    def public(self) -> dict:
        return {"staff_id": self.staff_id, "display_name": self.display_name, "role": self.role}


def normalize_staff_id(staff_id: object) -> str:
    return staff_id.strip().lower() if isinstance(staff_id, str) else ""


def load_users(path: Path = DEFAULT_USERS_FILE) -> Dict[str, User]:
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    users: Dict[str, User] = {}
    for item in raw.get("users", []):
        user = User(
            staff_id=normalize_staff_id(item["staff_id"]),
            display_name=item["display_name"],
            role=item.get("role", "clinician"),
            password_hash=item["password_hash"],
            pin_hash=item["pin_hash"],
        )
        users[user.staff_id] = user
    return users


# --------------------------------------------------------------------------
# Audit log (append-only JSONL with a SHA-256 hash chain)
# --------------------------------------------------------------------------
FORBIDDEN_AUDIT_KEYS = frozenset({
    "pin", "password", "token", "secret", "pin_hash", "password_hash", "authorization", "cookie",
})


class AuditLog:
    """Append-only audit trail. Never pass secrets; known secret keys are dropped anyway.

    Each line carries ``prev`` (hash of the previous line) and ``hash`` so that a
    deleted or edited line is detectable with :meth:`verify_chain`.
    """

    def __init__(self, path: Path = DEFAULT_AUDIT_FILE, wall_clock: Callable[[], float] = time.time):
        self.path = Path(path)
        self._wall_clock = wall_clock
        self._lock = threading.Lock()
        self._last_hash = self._read_last_hash()

    def _read_last_hash(self) -> str:
        try:
            with open(self.path, "rb") as fh:
                lines = fh.read().splitlines()
            for line in reversed(lines):
                if line.strip():
                    return json.loads(line).get("hash", "")
        except (FileNotFoundError, ValueError):
            pass
        return ""

    def record(self, event: str, staff_id: Optional[str] = None, **details) -> dict:
        ts = datetime.fromtimestamp(self._wall_clock(), tz=timezone.utc).isoformat(timespec="milliseconds")
        entry = {"ts": ts.replace("+00:00", "Z"), "event": event, "staff_id": staff_id}
        for key, value in details.items():
            if key.lower() in FORBIDDEN_AUDIT_KEYS or value is None:
                continue
            entry[key] = value
        with self._lock:
            entry["prev"] = self._last_hash
            body = json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            entry["hash"] = _sha256_hex(body)
            line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(fd, line.encode("utf-8"))
            finally:
                os.close(fd)
            self._last_hash = entry["hash"]
        return entry

    def entries(self) -> List[dict]:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                return [json.loads(l) for l in fh if l.strip()]
        except FileNotFoundError:
            return []

    def tail(self, limit: int = 50) -> List[dict]:
        """Newest first."""
        limit = max(1, min(int(limit), 500))
        return list(reversed(self.entries()[-limit:]))

    def verify_chain(self) -> bool:
        prev = ""
        for entry in self.entries():
            claimed = entry.pop("hash", None)
            if entry.get("prev") != prev:
                return False
            body = json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            if claimed != _sha256_hex(body):
                return False
            prev = claimed
        return True


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------
class AuthError(Exception):
    """Carries an HTTP status, a machine code and a user-safe message."""

    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra

    def to_dict(self) -> dict:
        return {"error": self.code, "message": self.message, **self.extra}


@dataclass
class Session:
    token: str
    user: User
    created: float
    last_activity: float
    locked: bool = False
    lock_reason: Optional[str] = None
    pin_failures: int = 0

    @property
    def ref(self) -> str:
        """Short non-secret id for correlating audit lines (never the token itself)."""
        return _sha256_hex(self.token)[:12]


@dataclass
class _Throttle:
    failures: int = 0
    lockouts: int = 0
    locked_until: float = 0.0


class AuthService:
    """In-memory session store. All times come from the injectable ``clock`` (seconds)."""

    def __init__(
        self,
        users: Dict[str, User],
        audit: AuditLog,
        *,
        clock: Callable[[], float] = time.monotonic,
        idle_seconds: float = IDLE_LOCK_SECONDS,
        max_session_seconds: float = MAX_SESSION_SECONDS,
        max_pin_attempts: int = MAX_PIN_ATTEMPTS,
        login_max_failures: int = LOGIN_MAX_FAILURES,
        login_lockout_seconds: float = LOGIN_LOCKOUT_SECONDS,
        login_lockout_max_seconds: float = LOGIN_LOCKOUT_MAX_SECONDS,
    ):
        self.users = users
        self.audit = audit
        self.clock = clock
        self.idle_seconds = idle_seconds
        self.max_session_seconds = max_session_seconds
        self.max_pin_attempts = max_pin_attempts
        self.login_max_failures = login_max_failures
        self.login_lockout_seconds = login_lockout_seconds
        self.login_lockout_max_seconds = login_lockout_max_seconds
        self._sessions: Dict[str, Session] = {}
        self._throttles: Dict[str, _Throttle] = {}
        self._lock = threading.RLock()
        # Verified against for unknown staff IDs so timing does not reveal who exists.
        self._dummy_hash = hash_secret(secrets.token_urlsafe(16))

    # -- policy ------------------------------------------------------------
    def policy(self) -> dict:
        return {
            "idle_seconds": self.idle_seconds,
            "max_session_seconds": self.max_session_seconds,
            "max_pin_attempts": self.max_pin_attempts,
            "login_max_failures": self.login_max_failures,
            "login_lockout_seconds": self.login_lockout_seconds,
            "pin_length": PIN_LENGTH,
        }

    # -- login -------------------------------------------------------------
    def login(self, staff_id: object, password: object, *, client: Optional[str] = None) -> Session:
        sid = normalize_staff_id(staff_id)
        if not sid or not isinstance(password, str) or not password or len(sid) > 64 or len(password) > 256:
            raise AuthError(400, "bad_request", "Enter your staff ID and password.")

        now = self.clock()
        with self._lock:
            throttle = self._throttles.get(sid)
            if throttle and throttle.locked_until > now:
                retry = math.ceil(throttle.locked_until - now)
                self.audit.record("login_blocked", sid, retry_after=retry, client=client)
                raise AuthError(429, "rate_limited",
                                f"Too many failed attempts. Try again in {retry} s.", retry_after=retry)

        user = self.users.get(sid)
        ok = verify_secret(password, user.password_hash if user else self._dummy_hash) and user is not None

        with self._lock:
            now = self.clock()
            if not ok:
                t = self._throttles.setdefault(sid, _Throttle())
                t.failures += 1
                extra = {}
                if t.failures >= self.login_max_failures:
                    t.lockouts += 1
                    t.failures = 0
                    duration = min(self.login_lockout_seconds * (2 ** (t.lockouts - 1)),
                                   self.login_lockout_max_seconds)
                    t.locked_until = now + duration
                    extra["lockout_seconds"] = duration
                self.audit.record("login_failed", sid, client=client, **extra)
                raise AuthError(401, "invalid_credentials", "Staff ID or password is incorrect.")

            self._throttles.pop(sid, None)
            token = secrets.token_urlsafe(TOKEN_BYTES)
            session = Session(token=token, user=user, created=now, last_activity=now)
            self._sessions[_sha256_hex(token)] = session
            self.audit.record("login", sid, session=session.ref, client=client)
            self._purge_expired_locked(now)
            return session

    # -- lookup ------------------------------------------------------------
    def _get(self, token: Optional[str]) -> Session:
        """Return the live session (possibly locked) or raise 401. Caller holds ``_lock``."""
        if not token or not isinstance(token, str) or len(token) > 256:
            raise AuthError(401, "unauthenticated", "Please sign in.")
        session = self._sessions.get(_sha256_hex(token))
        if session is None or not hmac.compare_digest(session.token, token):
            raise AuthError(401, "unauthenticated", "Please sign in.")
        now = self.clock()
        if now - session.created >= self.max_session_seconds:
            self._sessions.pop(_sha256_hex(token), None)
            self.audit.record("session_expired", session.user.staff_id, session=session.ref)
            raise AuthError(401, "session_expired", "Your session has ended. Please sign in again.")
        if not session.locked and now - session.last_activity >= self.idle_seconds:
            session.locked = True
            session.lock_reason = "idle"
            self.audit.record("idle_lock", session.user.staff_id, session=session.ref, source="server")
        return session

    def _locked_error(self, session: Session) -> AuthError:
        return AuthError(423, "locked", "Session locked. Enter your PIN.",
                         reason=session.lock_reason,
                         attempts_left=self.max_pin_attempts - session.pin_failures)

    def authorize(self, token: Optional[str]) -> Session:
        """Gate for any endpoint that returns patient data. Counts as user activity.

        Raises AuthError 401 (sign in) or 423 (locked: show PIN pad).
        """
        with self._lock:
            session = self._get(token)
            if session.locked:
                raise self._locked_error(session)
            session.last_activity = self.clock()
            return session

    def status(self, token: Optional[str]) -> dict:
        """Read-only view; does NOT count as activity (so polling cannot keep a session open)."""
        with self._lock:
            try:
                session = self._get(token)
            except AuthError as err:
                return {"authenticated": False, "reason": err.code, "policy": self.policy()}
            now = self.clock()
            return {
                "authenticated": True,
                "locked": session.locked,
                "lock_reason": session.lock_reason,
                "user": session.user.public(),
                "attempts_left": self.max_pin_attempts - session.pin_failures,
                "idle_remaining": 0 if session.locked else
                max(0, round(self.idle_seconds - (now - session.last_activity))),
                "session_remaining": max(0, round(self.max_session_seconds - (now - session.created))),
                "policy": self.policy(),
            }

    # -- lock / unlock -----------------------------------------------------
    def lock(self, token: Optional[str], reason: str = "manual") -> Session:
        reason = reason if reason in {"manual", "idle", "hidden", "server"} else "manual"
        with self._lock:
            session = self._get(token)
            if not session.locked:
                session.locked = True
                session.lock_reason = reason
                event = "idle_lock" if reason == "idle" else "lock"
                self.audit.record(event, session.user.staff_id, session=session.ref, reason=reason)
            return session

    def unlock(self, token: Optional[str], pin: object) -> Session:
        with self._lock:
            session = self._get(token)
            if not session.locked:
                session.last_activity = self.clock()
                return session

        ok = is_valid_pin(pin) and verify_secret(pin, session.user.pin_hash)

        with self._lock:
            session = self._get(token)  # re-check: may have been revoked meanwhile
            if ok:
                session.locked = False
                session.lock_reason = None
                session.pin_failures = 0
                session.last_activity = self.clock()
                self.audit.record("unlock", session.user.staff_id, session=session.ref)
                return session
            session.pin_failures += 1
            left = self.max_pin_attempts - session.pin_failures
            self.audit.record("unlock_failed", session.user.staff_id, session=session.ref, attempts_left=left)
            if left <= 0:
                self._sessions.pop(_sha256_hex(session.token), None)
                self.audit.record("session_revoked", session.user.staff_id, session=session.ref,
                                  reason="too_many_pin_attempts")
                raise AuthError(401, "session_revoked",
                                "Too many incorrect PINs. Please sign in again with your password.")
            raise AuthError(403, "wrong_pin", "Incorrect PIN.", attempts_left=left)

    def logout(self, token: Optional[str], reason: str = "user") -> bool:
        if not token or not isinstance(token, str):
            return False
        with self._lock:
            session = self._sessions.get(_sha256_hex(token))
            if session is None or not hmac.compare_digest(session.token, token):
                return False
            self._sessions.pop(_sha256_hex(token), None)
            reason = reason if reason in {"user", "pagehide", "not_me", "expired"} else "user"
            self.audit.record("logout", session.user.staff_id, session=session.ref, reason=reason)
            return True

    # -- data access audit ---------------------------------------------------
    def record_data_access(self, session: Session, patient_id: str, task_text: str = "", **extra) -> dict:
        """Log that ``session`` viewed ``patient_id``. The task text is stored only as a SHA-256 hash."""
        return self.audit.record(
            "data_access", session.user.staff_id, session=session.ref,
            patient_id=str(patient_id)[:64],
            task_sha256=_sha256_hex((task_text or "").strip()),
            **extra,
        )

    # -- housekeeping ------------------------------------------------------
    def _purge_expired_locked(self, now: float) -> None:
        for key in [k for k, s in self._sessions.items() if now - s.created >= self.max_session_seconds]:
            self._sessions.pop(key, None)

    def active_session_count(self) -> int:
        with self._lock:
            return len(self._sessions)


def default_service(users_file: Path = DEFAULT_USERS_FILE, audit_file: Path = DEFAULT_AUDIT_FILE,
                    **kwargs) -> AuthService:
    return AuthService(load_users(users_file), AuditLog(audit_file), **kwargs)


__all__: Iterable[str] = [
    "AuthService", "AuthError", "AuditLog", "Session", "User", "hash_secret", "verify_secret",
    "is_valid_pin", "load_users", "default_service",
]
