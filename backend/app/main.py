"""HTTP API.

    uvicorn app.main:app --port 8000                      (from backend/)
    uvicorn --app-dir backend app.main:app --port 8000    (from the repo root)

Default backend: the deterministic engine (engine/ over data/build/, see app/adapter.py).
SECOND_LOOK_BACKEND=llm switches to the LLM-extracted store in cache/ (app/query.py).
"""
import base64
import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from . import store
from .auth import AuthHTTPError, auth_error_handler, require_unlocked, router as auth_router, service as auth_service
from .schema import Briefing, BriefingRequest
from security.auth import Session

PATIENT_ID = os.environ.get("PATIENT_ID", "patient-0000-0001")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Build data/build/ if missing and load it once, so the first briefing is fast."""
    if store.use_engine():
        store.documents()
        store.segments()
    if os.environ.get("EVAL_ON_START") in ("1", "probe"):  # opt-in self-test, printed to the logs ("EVAL:" lines)
        try:
            from eval.selftest import start_background
            start_background(mode=os.environ["EVAL_ON_START"])
        except Exception as e:  # never stop the app over the self-test
            print("EVAL: self-test not started: %r" % (e,), flush=True)
    yield


app = FastAPI(title="Second Eye API", lifespan=lifespan)
# No CORS middleware: the app is served from the same origin (STATIC_DIR, or the Vite dev proxy).
app.add_exception_handler(AuthHTTPError, auth_error_handler)
app.include_router(auth_router)

# Optional legacy gate (off by default): SITE_GATE=basic plus SITE_USER/SITE_PASSWORD puts HTTP Basic auth in
# front of everything except /health. Sign-in and the PIN lock (app/auth.py) replace it (docs/DECISIONS.md, 11).
SITE_GATE = os.environ.get("SITE_GATE", "").lower() == "basic"
SITE_USER = os.environ.get("SITE_USER", "")
SITE_PASSWORD = os.environ.get("SITE_PASSWORD", "")


@app.middleware("http")
async def headers_and_gate(request: Request, call_next):
    if SITE_GATE and SITE_PASSWORD and request.url.path != "/health":
        expected = "Basic " + base64.b64encode(f"{SITE_USER}:{SITE_PASSWORD}".encode()).decode()
        if not hmac.compare_digest(request.headers.get("authorization", ""), expected):
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Second Eye"'})
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


def audit_access(session: Session, resource: str, task: str = "", **extra) -> None:
    """data_access audit line: who, which patient, which resource; the task only as a SHA-256 hash."""
    auth_service.record_data_access(session, PATIENT_ID, task, resource=resource, **extra)


@app.get("/health")
def health() -> dict:
    from engine import llm
    s = llm.status()
    return {"ok": True, "backend": store.BACKEND, "documents": len(store.documents()),
            "facts": store.facts_count(),
            "llm": {k: s[k] for k in ("enabled", "calls_today", "spend_eur_est", "budget_eur")}}


@app.get("/documents")
def documents(session: Session = Depends(require_unlocked)) -> list[dict]:
    audit_access(session, "documents")
    return [d.model_dump(exclude={"text"}) for d in store.documents()]


@app.get("/documents/{doc_id}")
def document(doc_id: str, session: Session = Depends(require_unlocked)) -> dict:
    audit_access(session, "document", doc_id=doc_id[:64])
    doc = next((d for d in store.documents() if d.id == doc_id), None)
    if not doc:
        raise HTTPException(404, "unknown document")
    segs = [s.model_dump() for s in store.segments() if s.doc_id == doc_id]
    return {**doc.model_dump(), "segments": segs}


@app.get("/segments/{segment_id}")
def segment(segment_id: str, session: Session = Depends(require_unlocked)) -> dict:
    audit_access(session, "segment", segment_id=segment_id[:64])
    seg = next((s for s in store.segments() if s.id == segment_id), None)
    if not seg:
        raise HTTPException(404, "unknown segment")
    return seg.model_dump()


@app.post("/briefing", response_model=Briefing)
def briefing(req: BriefingRequest, session: Session = Depends(require_unlocked)) -> Briefing:
    audit_access(session, "briefing", req.situation, detail=req.detail)
    return store.briefing(req.situation, req.detail)


# Deployment: serve the built mobile app (mobile/dist) from the same origin, registered last so API routes win.
# SPA fallback: an unknown GET path that is not an API path returns index.html, so deep links (/results) work.
API_PREFIXES = ("auth", "briefing", "documents", "segments", "health", "docs", "redoc", "openapi.json")
STATIC_DIR = Path(os.environ["STATIC_DIR"]).resolve() if os.environ.get("STATIC_DIR") else None

if STATIC_DIR:
    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def frontend(path: str):
        first = path.split("/", 1)[0]
        if first in API_PREFIXES:
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = (STATIC_DIR / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(STATIC_DIR):
            # Hashed bundles can be cached for good; everything else is revalidated.
            cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
            return FileResponse(candidate, headers={"Cache-Control": cache})
        if "." in path.rsplit("/", 1)[-1]:
            return JSONResponse({"detail": "Not Found"}, status_code=404)  # missing file, not a page route
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})
