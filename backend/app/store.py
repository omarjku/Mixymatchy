"""Read/write the precomputed fact store in cache/ (git-ignored)."""
import json

from .config import CACHE_DIR
from .schema import Document, Fact, Finding, Segment

FILES = {"documents": Document, "segments": Segment, "facts": Fact, "findings": Finding}


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
