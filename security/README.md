# Second Look: access security

This module handles sign-in, the PIN lock screen, idle and tab-hidden locking, and an append-only audit trail. It is built for a shared clinical workstation or tablet. The backend uses only the Python 3 standard library, and the frontend is plain HTML, CSS and JS with no build step and no CDN. You can drop it into any frontend, including Next.js.

```bash
python3 -m security.server --port 8700        # demo at http://localhost:8700
python3 -m unittest security.test_security -v  # 24 tests
```

Open `http://localhost:8700/?idle=5` to shorten the client idle lock to 5 s for a live demo.

## In the app (FastAPI)

The deployed app does not run `server.py`. `backend/app/auth.py` mounts the same `/auth/*` API inside FastAPI around `AuthService`, and `/briefing`, `/documents` and `/segments` depend on `require_unlocked` (401 = sign in, 423 = PIN). Each of those calls writes a `data_access` audit line (task text only as SHA-256). `/health` stays public. The mobile app bundles verbatim copies of `web/second-look-lock.js` and `web/lock.css` in `mobile/src/second-look/` (a test checks they match; re-copy after editing). Users come from `SECOND_LOOK_USERS`, else the secret file `/etc/secrets/users.json`, else `users.example.json`. `SECOND_LOOK_IDLE_SECONDS` overrides the server idle lock; `?idle=10` in the app URL shortens the client idle lock for a demo.

## Demo credentials

| Staff ID | Password | PIN | Role |
|---|---|---|---|
| `dr.demo` | `SecondLook-demo-2026` | `2468` | anaesthetist |

These credentials are for the demo only. `security/users.example.json` stores only salted PBKDF2-SHA256 hashes (240k iterations). To add a user:

```bash
python3 -m security.add_user --staff-id nurse.kim --name "Kim Lee" --role nurse   # prompts for password + PIN
```

## How it works

```
Login (staff ID + password) ──► App unlocked ──(3 min idle / Lock button / tab hidden / server 423)──► PIN lock
      ▲                              ▲                                                                    │
      │                              └──────────────────────── correct PIN ◄─────────────────────────────┘
      └── logout · "Not you?" · 5 wrong PINs · 12 h max · page reload/close ◄──────────────────────────────┘
```

* **Server (`auth.py`, `server.py`).** A successful login creates a `secrets.token_urlsafe(32)` token. The session lives only in memory, keyed by the token's SHA-256 and compared with `hmac.compare_digest`. The token is returned in JSON for bearer clients. It is also set as an `HttpOnly; SameSite=Strict` cookie for cookie clients. Every protected request goes through `AuthService.authorize(token)`, which returns **401** (sign in), **423** (locked: show the PIN pad), or the session. Each authorised request counts as activity. The server enforces the idle lock itself from `last_activity`, so a client that skips its timer is still locked.
* **Client (`web/second-look-lock.js`).** The token is kept only in a JS closure. It is never written to localStorage, sessionStorage or a JS-readable cookie, so reloading the page always means a full sign-in. On `pagehide`, the client sends a `sendBeacon` logout that revokes the session on the server. When the page becomes hidden (`visibilitychange`), the app is blurred straight away (CSS filter, `inert`) and locked, so the app-switcher snapshot shows nothing. While the user is active (pointer, key, touch, wheel, scroll), the client sends a heartbeat at most every 30 s to keep the server's idle timer in step.
* **Audit (`data/audit/audit.jsonl`, gitignored).** One JSON line per event, written with `O_APPEND` and file mode `0600`. Each line carries the SHA-256 hash of the previous line, so `AuditLog.verify_chain()` detects a line that was edited or deleted. Events: `login`, `login_failed`, `login_blocked`, `unlock`, `unlock_failed`, `lock`, `idle_lock`, `logout`, `session_revoked`, `session_expired`, `data_access`. A `data_access` line records `patient_id` and `task_sha256`, never the task text. The log never contains passwords, PINs or tokens; keys with those names are also dropped defensively. Sessions are identified by a 12-character hash prefix.

## Policy

All values are constants at the top of `security/auth.py`. Each one can also be overridden per `AuthService(...)`.

| Rule | Value | Effect |
|---|---|---|
| Idle lock | 3 min (`IDLE_LOCK_SECONDS`) | The client locks after 3 min with no input. The server returns 423 once `last_activity` is older than that. |
| Hidden tab or app switch | immediate | The app is blurred and locked; the PIN is needed on return. |
| Max session | 12 h (`MAX_SESSION_SECONDS`) | The session is ended and a full login is needed. |
| Wrong PINs | 5 (`MAX_PIN_ATTEMPTS`) | The session is revoked and a password login is needed. Each failure shows the number of attempts left. |
| Login failures | 5 per staff ID → 60 s lockout, doubling, capped at 15 min | Returns 429 with `Retry-After`. Unknown IDs are throttled the same way and take the same time (a dummy hash is checked). |
| Hashing | PBKDF2-HMAC-SHA256, 16-byte salt, 240k iterations (minimum 200k) | Used for both password and PIN. |
| Page reload or close | full login | The token is only in memory, and the beacon logout revokes the session. |

## API

| Method and path | Auth | Notes |
|---|---|---|
| `POST /auth/login` `{staff_id,password}` | none | Returns `{token,user,expires_in,policy}` and sets the cookie. Errors: 401 or 429. |
| `POST /auth/unlock` `{pin}` | token | 200; 403 `{attempts_left}`; 401 `session_revoked` |
| `POST /auth/lock` `{reason}` | token | `reason`: `manual`, `idle` or `hidden` |
| `POST /auth/logout` | token | Also accepts a `text/plain` body `{token}` (sendBeacon). |
| `GET /auth/status` | token (optional) | Read-only; does not reset the idle timer. |
| `POST /auth/heartbeat` | unlocked | Counts as activity. |
| `GET /auth/audit?limit=50` | unlocked | Newest first, plus `chain_ok`. This endpoint is for the demo only; in production, restrict it to an auditor role. |
| `GET /api/ping` | unlocked | Example protected endpoint. |
| `POST /api/patient-access` `{patient_id,task}` | unlocked | Example of how to log a `data_access` event. |

The token can be sent as `Authorization: Bearer <token>` (preferred) or as the cookie. A POST authenticated by cookie must have `Content-Type: application/json`, which guards against CSRF.

### Protecting your own endpoint

```python
# inside security/server.py (stdlib server)
@require_unlocked
def api_patient_screen(self):
    self.auth.record_data_access(self.session, patient_id, task_text)
    ...
# any other Python backend
session = auth_service.authorize(token)   # raises AuthError(.status 401/423, .to_dict())
```

## Using it from another frontend (e.g. Next.js)

Start the server with your origin allowed. `http://localhost:3000` is allowed by default.

```bash
python3 -m security.server --allow-origin http://localhost:5173
```

```html
<script src="http://localhost:8700/second-look-lock.js"></script>   <!-- next/script, strategy="beforeInteractive" -->
```

```js
SecondLook.lock.init({
  apiBase: 'http://localhost:8700',
  appRoot: '#patient-app',                  // blurred and inert while locked or signed out
  onUnlocked: (user) => loadPatientScreen(),
  onLocked: (reason) => clearPatientDom(),   // optional: drop PHI from the DOM
  onLoggedOut: (reason) => clearPatientDom(),
  // idleSeconds: 180, lockOnHidden: true, heartbeatSeconds: 30, stylesheet: false, trustedOrigins: []
});
const res = await SecondLook.lock.fetch('/api/ping');  // adds the token; on 423 shows the PIN pad, on 401 shows login (and throws)
```

The module adds its own `lock.css` from `apiBase`; pass `stylesheet: false` to skip that. It also exposes `lock()`, `logout()`, `getUser()`, `getState()` and `isUnlocked()`. `fetch` refuses to attach the token to any origin other than `apiBase`, the page origin, or `trustedOrigins`.

## Files

| File | Purpose |
|---|---|
| `auth.py` | Policy constants, hashing, `AuthService` (sessions, PIN, rate limit) and `AuditLog`. |
| `server.py` | `http.server` API, the `require_unlocked` decorator, static files and security headers (CSP, `X-Frame-Options`, `no-store`). |
| `add_user.py` | CLI to add or replace users. |
| `users.example.json` | Demo user (hashes only). |
| `web/second-look-lock.js` | Reusable login and lock module (`window.SecondLook.lock`). |
| `web/lock.css` | Module styles (`sl-*`) and demo-page styles (`app-*`). Teal `#0f766e`, with dark mode. |
| `web/index.html`, `web/lock.js` | Demo host page: placeholder patient screen and audit viewer. |
| `test_security.py` | Unit and HTTP tests using an injectable clock. |

## Production notes (not done in this demo)

* **Identity.** Replace the passwords in the JSON file with hospital SSO (SAML or OIDC against AD/Entra ID). Use smartcard or badge tap-in (for example Imprivata) for fast user switching. Keep the PIN or badge as the *unlock* factor and SSO as the *login* factor.
* **HTTPS only.** Run behind TLS. Start the server with `--secure-cookie`, add HSTS, and never send tokens over plain HTTP. A phone on the ward network must reach the server over HTTPS.
* **Session store.** Move sessions to a persistent shared store (Redis or a database) with TTLs so they survive restarts and work across several workers. Bind sessions to a device where possible, and add per-IP throttling as well as per-ID throttling.
* **Secrets.** PINs have only 10,000 values, so a stolen hash file is weak without protection. Add a server-side pepper or HSM, keep the user store out of the repository, and rotate it.
* **Audit.** Ship lines to WORM or SIEM storage (append-only bucket, syslog) and anchor the hash chain periodically. Restrict `/auth/audit` to auditors. Define a retention policy that follows local law.
* **Devices.** Enroll tablets in MDM (Intune or Jamf): enforce an OS lock, kiosk or guided-access mode, disable screenshots in the managed browser, allow remote wipe, and do not cache patient data. The web idle lock adds to the OS lock; it does not replace it.
* **Hardening.** Use a strict CSP on the host app, which should store nothing in web storage. Add a review of the clinical idle timeout per ward (3 min suits shared terminals, while an operating room may need a different value).
