"""HTTP API.  uvicorn app.main:app --reload --port 8000  (run from backend/)"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import store
from .query import build_briefing
from .schema import Briefing, BriefingRequest

app = FastAPI(title="Second Look API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health() -> dict:
    return {"ok": True, "documents": len(store.load("documents")), "facts": len(store.load("facts"))}


@app.get("/documents")
def documents() -> list[dict]:
    return [d.model_dump(exclude={"text"}) for d in store.load("documents")]


@app.get("/documents/{doc_id}")
def document(doc_id: str) -> dict:
    doc = next((d for d in store.load("documents") if d.id == doc_id), None)
    if not doc:
        raise HTTPException(404, "unknown document")
    segs = [s.model_dump() for s in store.load("segments") if s.doc_id == doc_id]
    return {**doc.model_dump(), "segments": segs}


@app.get("/segments/{segment_id}")
def segment(segment_id: str) -> dict:
    seg = next((s for s in store.load("segments") if s.id == segment_id), None)
    if not seg:
        raise HTTPException(404, "unknown segment")
    return seg.model_dump()


@app.post("/briefing", response_model=Briefing)
def briefing(req: BriefingRequest) -> Briefing:
    return build_briefing(req.situation)
