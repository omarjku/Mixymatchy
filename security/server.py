"""Second Look access-security HTTP server (stdlib only).

    python3 -m security.server --port 8700      # demo at http://localhost:8700

Serves the auth API under /auth/*, an example protected API under /api/*, and
the lock-screen frontend (security/web/) at /.

Add your own protected endpoint by decorating a handler method::

    @require_unlocked
    def api_patient(self):
        self.auth.record_data_access(self.session, patient_id, task_text)
        self.send_json(200, {...})

and registering it in ``ROUTES``.
"""

from __future__ import annotations

import argparse
import functools
import json
import sys
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlsplit

from .auth import (DEFAULT_AUDIT_FILE, DEFAULT_USERS_FILE, IDLE_LOCK_SECONDS, AuditLog, AuthError,
                   AuthService, load_users)

COOKIE_NAME = "sl_session"
MAX_BODY_BYTES = 16 * 1024
WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/lock.css": ("lock.css", "text/css; charset=utf-8"),
    "/lock.js": ("lock.js", "text/javascript; charset=utf-8"),
    "/second-look-lock.js": ("second-look-lock.js", "text/javascript; charset=utf-8"),
}
DEFAULT_ALLOWED_ORIGINS = ("http://localhost:3000", "http://127.0.0.1:3000")


def require_unlocked(handler):
    """Decorator for handler methods: 401 if not signed in, 423 if locked.

    On success ``self.session`` is the caller's :class:`~security.auth.Session`
    and the request counts as user activity (resets the idle timer).
    """

    @functools.wraps(handler)
    def wrapper(self: "SecurityHandler", *args, **kwargs):
        try:
            self.session = self.auth.authorize(self.request_token())
        except AuthError as err:
            return self.send_auth_error(err)
        return handler(self, *args, **kwargs)

    return wrapper


class SecurityHandler(BaseHTTPRequestHandler):
    server_version = "SecondLookSecurity/1.0"
    sys_version = ""
    auth: AuthService  # injected via make_server
    allowed_origins: tuple = DEFAULT_ALLOWED_ORIGINS
    secure_cookie: bool = False
    session = None

    # ------------------------------------------------------------ plumbing
    def log_message(self, fmt, *args):  # paths/status only, never bodies
        sys.stderr.write("[security] %s %s\n" % (self.address_string(), fmt % args))

    @property
    def path_only(self) -> str:
        return urlsplit(self.path).path

    @property
    def query(self) -> dict:
        return parse_qs(urlsplit(self.path).query)

    def _cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if origin and origin in self.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Vary", "Origin")

    def _security_headers(self, html: bool = False) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if html:
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; img-src 'self' data:; object-src 'none'; "
                             "base-uri 'none'; frame-ancestors 'none'; form-action 'self'")

    def send_json(self, status: int, payload: dict, extra_headers: Optional[dict] = None) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self._cors_headers()
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_auth_error(self, err: AuthError) -> None:
        headers = {}
        if err.status == 429 and "retry_after" in err.extra:
            headers["Retry-After"] = str(err.extra["retry_after"])
        if err.status == 401:
            headers["Set-Cookie"] = self._cookie("", max_age=0)
        self.send_json(err.status, err.to_dict(), headers)

    def _cookie(self, value: str, max_age: Optional[int] = None) -> str:
        parts = [f"{COOKIE_NAME}={value}", "Path=/", "HttpOnly", "SameSite=Strict"]
        if max_age is not None:
            parts.append(f"Max-Age={max_age}")
        if self.secure_cookie:
            parts.append("Secure")
        return "; ".join(parts)

    def read_json(self, allow_text_plain: bool = False) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            raise AuthError(413, "too_large", "Request body too large.")
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        raw = self.rfile.read(length) if length else b""
        if not raw:
            return {}
        if ctype != "application/json" and not (allow_text_plain and ctype in ("text/plain", "")):
            raise AuthError(415, "unsupported_media_type", "Send JSON (Content-Type: application/json).")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise AuthError(400, "bad_json", "Malformed JSON.")
        if not isinstance(data, dict):
            raise AuthError(400, "bad_json", "Expected a JSON object.")
        return data

    def request_token(self, body: Optional[dict] = None) -> Optional[str]:
        """Bearer header first (in-memory JS clients), then HttpOnly cookie."""
        header = self.headers.get("Authorization") or ""
        if header.lower().startswith("bearer "):
            return header[7:].strip() or None
        if body and isinstance(body.get("token"), str):  # only used for sendBeacon logout
            return body["token"]
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie") or "")
        except Exception:
            return None
        morsel = cookie.get(COOKIE_NAME)
        if morsel and morsel.value:
            if self.command == "POST":
                # CSRF guard for cookie auth: cross-site forms cannot send application/json.
                ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                if ctype != "application/json":
                    return None
            return morsel.value
        return None

    def client_label(self) -> str:
        return (self.headers.get("User-Agent") or "")[:80]

    # ------------------------------------------------------------ dispatch
    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method: str):
        path = self.path_only
        if method == "GET" and path in STATIC_FILES:
            return self.serve_static(*STATIC_FILES[path])
        name = ROUTES.get((method, path))
        if not name:
            return self.send_json(404, {"error": "not_found", "message": "No such endpoint."})
        try:
            getattr(self, name)()
        except AuthError as err:
            self.send_auth_error(err)
        except Exception as exc:  # never leak internals
            self.log_message("handler error %r", exc)
            self.send_json(500, {"error": "server_error", "message": "Internal error."})

    def serve_static(self, filename: str, ctype: str):
        data = (WEB_DIR / filename).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self._security_headers(html=filename.endswith(".html"))
        if not filename.endswith(".html"):
            # The reusable module and its CSS may be loaded by another origin (e.g. Next.js dev server).
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cross-Origin-Resource-Policy", "cross-origin")
        self.end_headers()
        self.wfile.write(data)

    # ------------------------------------------------------------ /auth/*
    def auth_login(self):
        body = self.read_json()
        session = self.auth.login(body.get("staff_id"), body.get("password"), client=self.client_label())
        self.send_json(200, {
            "token": session.token,
            "user": session.user.public(),
            "expires_in": self.auth.max_session_seconds,
            "policy": self.auth.policy(),
        }, {"Set-Cookie": self._cookie(session.token)})

    def auth_unlock(self):
        body = self.read_json()
        session = self.auth.unlock(self.request_token(), body.get("pin"))
        self.send_json(200, {"ok": True, "user": session.user.public()})

    def auth_lock(self):
        body = self.read_json()
        self.auth.lock(self.request_token(), str(body.get("reason") or "manual"))
        self.send_json(200, {"ok": True, "locked": True})

    def auth_logout(self):
        body = self.read_json(allow_text_plain=True)
        self.auth.logout(self.request_token(body), str(body.get("reason") or "user"))
        self.send_json(200, {"ok": True}, {"Set-Cookie": self._cookie("", max_age=0)})

    def auth_status(self):
        self.send_json(200, self.auth.status(self.request_token()))

    def auth_policy(self):
        self.send_json(200, self.auth.policy())

    @require_unlocked
    def auth_heartbeat(self):
        self.send_json(200, {"ok": True, "idle_seconds": self.auth.idle_seconds})

    @require_unlocked
    def auth_audit(self):
        try:
            limit = int(self.query.get("limit", ["50"])[0])
        except ValueError:
            limit = 50
        self.send_json(200, {"entries": self.auth.audit.tail(limit),
                             "chain_ok": self.auth.audit.verify_chain()})

    # ------------------------------------------------------------ /api/* examples
    @require_unlocked
    def api_ping(self):
        self.send_json(200, {"ok": True, "pong": True, "user": self.session.user.public()})

    @require_unlocked
    def api_patient_access(self):
        """Example of logging a data access. Real endpoints call record_data_access the same way."""
        body = self.read_json()
        patient_id = str(body.get("patient_id") or "").strip()
        if not patient_id:
            raise AuthError(400, "bad_request", "patient_id is required.")
        self.auth.record_data_access(self.session, patient_id, str(body.get("task") or ""))
        self.send_json(200, {"ok": True, "patient_id": patient_id})


ROUTES = {
    ("POST", "/auth/login"): "auth_login",
    ("POST", "/auth/unlock"): "auth_unlock",
    ("POST", "/auth/lock"): "auth_lock",
    ("POST", "/auth/logout"): "auth_logout",
    ("POST", "/auth/heartbeat"): "auth_heartbeat",
    ("GET", "/auth/status"): "auth_status",
    ("GET", "/auth/policy"): "auth_policy",
    ("GET", "/auth/audit"): "auth_audit",
    ("GET", "/api/ping"): "api_ping",
    ("POST", "/api/patient-access"): "api_patient_access",
}


def make_server(auth: AuthService, host: str = "127.0.0.1", port: int = 8700,
                allowed_origins=DEFAULT_ALLOWED_ORIGINS, secure_cookie: bool = False) -> ThreadingHTTPServer:
    handler = type("BoundSecurityHandler", (SecurityHandler,), {
        "auth": auth, "allowed_origins": tuple(allowed_origins), "secure_cookie": secure_cookie,
    })
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Second Look access-security demo server")
    p.add_argument("--host", default="127.0.0.1", help="Use 0.0.0.0 to test from a phone on your LAN")
    p.add_argument("--port", type=int, default=8700)
    p.add_argument("--users", type=Path, default=DEFAULT_USERS_FILE)
    p.add_argument("--audit", type=Path, default=DEFAULT_AUDIT_FILE)
    p.add_argument("--idle-seconds", type=float, default=IDLE_LOCK_SECONDS,
                   help="Server-side idle lock (default 180)")
    p.add_argument("--allow-origin", action="append", default=None,
                   help="Extra CORS origin for a separate frontend (repeatable)")
    p.add_argument("--secure-cookie", action="store_true", help="Add Secure to the cookie (behind HTTPS)")
    args = p.parse_args(argv)

    auth = AuthService(load_users(args.users), AuditLog(args.audit), idle_seconds=args.idle_seconds)
    origins = DEFAULT_ALLOWED_ORIGINS + tuple(args.allow_origin or ())
    server = make_server(auth, args.host, args.port, origins, args.secure_cookie)
    print(f"Second Look security demo on http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}"
          f"  (users: {len(auth.users)}, audit: {args.audit})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
