"""HTTP API.

    uvicorn app.main:app --port 8000                      (from backend/)
    uvicorn --app-dir backend app.main:app --port 8000    (from the repo root)

Default backend: the deterministic engine (engine/ over data/build/, see app/adapter.py).
SECOND_LOOK_BACKEND=llm switches to the LLM-extracted store in cache/ (app/query.py).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

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
