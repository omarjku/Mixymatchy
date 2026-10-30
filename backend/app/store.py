"""Where the API reads documents, segments and briefings from.

SECOND_LOOK_BACKEND=engine (default): deterministic engine via app/adapter.py, reading data/build/
                                      (built by pipeline/ + compare/ on first use if missing).
SECOND_LOOK_BACKEND=llm:              the LLM-extracted fact store in cache/ (python -m app.precompute,
                                      needs ANTHROPIC_API_KEY), answered by app/query.py.
"""
import json
import os

from .config import CACHE_DIR
from .schema import Briefing, Document, Fact, Finding, Segment

FILES = {"documents": Document, "segments": Segment, "facts": Fact, "findings": Finding}
BACKEND = os.getenv("SECOND_LOOK_BACKEND", "engine").lower()


def use_engine() -> bool:
    return BACKEND != "llm"


# ---------------------------------------------------------------- what the routes call

def documents() -> list[Document]:
    if use_engine():
        from . import adapter
        return adapter.documents()
    return load("documents")


def segments() -> list[Segment]:
    if use_engine():
        from . import adapter
        return adapter.segments()
    return load("segments")


def facts_count() -> int:
    if use_engine():
        from . import adapter
        return len(adapter.engine_store().facts)
    return len(load("facts"))


def briefing(situation: str, detail: str = "long") -> Briefing:
    if use_engine():
        from . import adapter
        return adapter.build_briefing(situation, detail=detail)
    from .query import build_briefing
    return build_briefing(situation)


# ---------------------------------------------------------------- LLM-store cache (cache/, git-ignored)

def save(name: str, items: list) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    (CACHE_DIR / f"{name}.json").write_text(
        json.dumps([i.model_dump() for i in items], ensure_ascii=False, indent=1), encoding="utf-8")


def save_raw(name: str, items: list) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    (CACHE_DIR / f"{name}.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


def load_raw(name: str) -> list:
    path = CACHE_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def load(name: str) -> list:
    path = CACHE_DIR / f"{name}.json"
    if not path.exists():
        return []
    return [FILES[name](**d) for d in json.loads(path.read_text(encoding="utf-8"))]
