"""Sign-in, PIN lock and audit inside FastAPI: an APIRouter around security.auth.AuthService.

    /auth/login  /auth/unlock  /auth/lock  /auth/logout  /auth/status  /auth/policy  /auth/heartbeat  /auth/audit

Patient-data routes depend on ``require_unlocked`` (401 = sign in, 423 = locked, PIN needed). The token is
sent as ``Authorization: Bearer`` by security/web/second-look-lock.js; an HttpOnly cookie is also accepted.

Users: SECOND_LOOK_USERS (path), else a Render secret file /etc/secrets/users.json (or
/etc/secrets/SECOND_LOOK_USERS), else the demo user in security/users.example.json.
Audit: SECOND_LOOK_AUDIT, default data/audit/audit.jsonl (ephemeral on Render, accepted for the demo).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from security.auth import (  # noqa: E402
    DEFAULT_AUDIT_FILE, IDLE_LOCK_SECONDS, AuditLog, AuthError, AuthService, Session, load_users,
)

COOKIE_NAME = "sl_session"
MAX_BODY_BYTES = 8 * 1024
SECRET_USER_FILES = (Path("/etc/secrets/users.json"), Path("/etc/secrets/SECOND_LOOK_USERS"))


def users_file() -> Path:
    if os.environ.get("SECOND_LOOK_USERS"):
        return Path(os.environ["SECOND_LOOK_USERS"])
    for path in SECRET_USER_FILES:
        if path.is_file() and path.stat().st_size:
            return path
    return ROOT / "security" / "users.example.json"


def build_service() -> AuthService:
    idle = float(os.environ.get("SECOND_LOOK_IDLE_SECONDS") or IDLE_LOCK_SECONDS)
    audit = Path(os.environ.get("SECOND_LOOK_AUDIT") or DEFAULT_AUDIT_FILE)
    return AuthService(load_users(users_file()), AuditLog(audit), idle_seconds=idle)


service: AuthService = build_service()
router = APIRouter(prefix="/auth", tags=["auth"])


class AuthHTTPError(Exception):
    def __init__(self, err: AuthError):
        self.err = err


def error_response(err: AuthError) -> JSONResponse:
    headers = {"Cache-Control": "no-store"}
    if err.status == 429 and "retry_after" in err.extra:
        headers["Retry-After"] = str(err.extra["retry_after"])
    resp = JSONResponse(err.to_dict(), status_code=err.status, headers=headers)
    if err.status == 401:
        resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


async def auth_error_handler(_request: Request, exc: AuthHTTPError) -> JSONResponse:
    return error_response(exc.err)


def _json(payload: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status, headers={"Cache-Control": "no-store"})


async def read_body(request: Request, allow_text_plain: bool = False) -> dict:
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise AuthHTTPError(AuthError(413, "too_large", "Request body too large."))
    if not raw:
        return {}
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ctype != "application/json" and not (allow_text_plain and ctype in ("text/plain", "")):
        raise AuthHTTPError(AuthError(415, "unsupported_media_type", "Send JSON (Content-Type: application/json)."))
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise AuthHTTPError(AuthError(400, "bad_json", "Malformed JSON."))
    if not isinstance(data, dict):
        raise AuthHTTPError(AuthError(400, "bad_json", "Expected a JSON object."))
    return data


def request_token(request: Request, body: Optional[dict] = None) -> Optional[str]:
    """Bearer header first, then the sendBeacon body (logout only), then the HttpOnly cookie."""
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    if body and isinstance(body.get("token"), str):
        return body["token"]
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie:
        if request.method != "GET":
            # CSRF guard for cookie auth: cross-site forms cannot send application/json.
            ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
            if ctype != "application/json":
                return None
        return cookie
    return None


def _client(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:80]


def _secure(request: Request) -> bool:
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


def require_unlocked(request: Request) -> Session:
    """Dependency for patient-data routes. Counts as user activity (resets the idle timer)."""
    try:
        return service.authorize(request_token(request))
    except AuthError as err:
        raise AuthHTTPError(err)


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except AuthError as err:
        raise AuthHTTPError(err)


@router.post("/login")
async def login(request: Request):
    body = await read_body(request)
    session = await run_in_threadpool(_call, service.login, body.get("staff_id"), body.get("password"), client=_client(request))
    resp = _json({"token": session.token, "user": session.user.public(),
                  "expires_in": service.max_session_seconds, "policy": service.policy()})
    resp.set_cookie(COOKIE_NAME, session.token, path="/", httponly=True, samesite="strict",
                    secure=_secure(request), max_age=int(service.max_session_seconds))
    return resp


@router.post("/unlock")
async def unlock(request: Request):
    body = await read_body(request)
    session = await run_in_threadpool(_call, service.unlock, request_token(request), body.get("pin"))
    return _json({"ok": True, "user": session.user.public()})


@router.post("/lock")
async def lock(request: Request):
    body = await read_body(request)
    _call(service.lock, request_token(request), str(body.get("reason") or "manual"))
    return _json({"ok": True, "locked": True})


@router.post("/logout")
async def logout(request: Request):
    body = await read_body(request, allow_text_plain=True)
    service.logout(request_token(request, body), str(body.get("reason") or "user"))
    resp = _json({"ok": True})
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


@router.get("/status")
def status(request: Request):
    return _json(service.status(request_token(request)))


@router.get("/policy")
def policy():
    return _json(service.policy())


@router.post("/heartbeat")
def heartbeat(_session: Session = Depends(require_unlocked)):
    return _json({"ok": True, "idle_seconds": service.idle_seconds})


@router.get("/audit")
def audit(limit: int = 50, _session: Session = Depends(require_unlocked)):
    # Demo only: in production restrict this to an auditor role.
    return _json({"entries": service.audit.tail(limit), "chain_ok": service.audit.verify_chain()})
