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

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from . import store
from .schema import Briefing, BriefingRequest


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Build data/build/ if missing and load it once, so the first briefing is fast."""
    if store.use_engine():
        store.documents()
        store.segments()
    yield


app = FastAPI(title="Second Look API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Deployment gate: the patient data must not be public, so a hosted instance sets SITE_USER and
# SITE_PASSWORD and every request (page, API, documents) needs them. Unset locally = no gate.
SITE_USER = os.environ.get("SITE_USER", "")
SITE_PASSWORD = os.environ.get("SITE_PASSWORD", "")


@app.middleware("http")
async def site_gate(request, call_next):
    if not SITE_PASSWORD or request.url.path == "/health":
        return await call_next(request)
    expected = "Basic " + base64.b64encode(f"{SITE_USER}:{SITE_PASSWORD}".encode()).decode()
    if hmac.compare_digest(request.headers.get("authorization", ""), expected):
        return await call_next(request)
    return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Second Look"'})


@app.get("/health")
def health() -> dict:
    return {"ok": True, "backend": store.BACKEND, "documents": len(store.documents()),
            "facts": store.facts_count()}


@app.get("/documents")
def documents() -> list[dict]:
    return [d.model_dump(exclude={"text"}) for d in store.documents()]


@app.get("/documents/{doc_id}")
def document(doc_id: str) -> dict:
    doc = next((d for d in store.documents() if d.id == doc_id), None)
    if not doc:
        raise HTTPException(404, "unknown document")
    segs = [s.model_dump() for s in store.segments() if s.doc_id == doc_id]
    return {**doc.model_dump(), "segments": segs}


@app.get("/segments/{segment_id}")
def segment(segment_id: str) -> dict:
    seg = next((s for s in store.segments() if s.id == segment_id), None)
    if not seg:
        raise HTTPException(404, "unknown segment")
    return seg.model_dump()


@app.post("/briefing", response_model=Briefing)
def briefing(req: BriefingRequest) -> Briefing:
    return store.briefing(req.situation)


# Deployment: serve the exported frontend from the same origin (registered last, so API routes win).
if os.environ.get("STATIC_DIR"):
    app.mount("/", StaticFiles(directory=os.environ["STATIC_DIR"], html=True), name="frontend")
