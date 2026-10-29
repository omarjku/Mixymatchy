"""Loading of build artefacts and rulebook, with the 'nothing made up' re-check.

Every fact is re-verified at load time: its quote must be a substring (up to
whitespace) of each linked passage, and each passage must be the exact slice of
its document's display_text.  Facts failing the check are dropped and counted.
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD_DIR = os.environ.get("SECOND_LOOK_BUILD", os.path.join(ROOT, "data", "build"))
RULEBOOK_DIR = os.environ.get("SECOND_LOOK_RULEBOOK", os.path.join(ROOT, "rulebook"))
RAW_DIR = os.path.join(ROOT, "data", "patient-0000-0001")


def _load(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


class Store:
    """Facts, passages, documents and contradictions of one patient build."""

    def __init__(self, build_dir=BUILD_DIR):
        self.build_dir = build_dir
        self.docs = _load(os.path.join(build_dir, "docs.json"), {}) or {}
        self.passages = _load(os.path.join(build_dir, "passages.json"), []) or []
        raw_facts = _load(os.path.join(build_dir, "facts.json"), []) or []
        self.passage_by_id = {p["id"]: p for p in self.passages}
        self.facts, self.removed = [], []
        for f in raw_facts:
            (self.facts if self._verify(f) else self.removed).append(f)
        self.fact_by_id = {f["id"]: f for f in self.facts}
        self.compare = _load(os.path.join(build_dir, "compare.json"), None)

    def _verify(self, f):
        q = f.get("quote") or ""
        pids = f.get("passage_ids") or []
        if not q.strip() or not pids:
            return False
        for pid in pids:
            p = self.passage_by_id.get(pid)
            if p is None:
                return False
            dt = (self.docs.get(p.get("doc_id")) or {}).get("display_text") or ""
            if dt[p["start"]:p["end"]] != p.get("text"):
                return False
            if q not in p["text"] and _ws(q) not in _ws(p["text"]):
                return False
        return True

    def fact_docs(self, f):
        return sorted({self.passage_by_id[p]["doc_id"] for p in f.get("passage_ids") or []
                       if p in self.passage_by_id})

    def doc_date(self, doc_id):
        return (self.docs.get(doc_id) or {}).get("date")

    def patient_sex(self):
        """Sex from document wording (German 'Patientin'/'Frau' vs 'Patient'/'Herr').
        Returns (sex, passage_id or None).  Falls back to the patient header file."""
        fem = re.compile(r"\b(Patientin|Frau)\b")
        nf = nm = 0
        first = None
        for p in self.passages:
            t = p.get("text") or ""
            if fem.search(t):
                nf += 1
                first = first or p["id"]
            if re.search(r"\bHerr\b", t):
                nm += 1
        if nf or nm:
            return ("female" if nf >= nm else "male"), first
        pj = _load(os.path.join(RAW_DIR, "patient.json"), {}) or {}
        return pj.get("sex"), None


def load_rulebook(rulebook_dir=RULEBOOK_DIR):
    roles = _load(os.path.join(rulebook_dir, "roles.json"), {}) or {}
    tasks = _load(os.path.join(rulebook_dir, "tasks.json"), {}) or {}
    return roles, tasks


_STORE = None
_RULEBOOK = None


def store():
    global _STORE
    if _STORE is None:
        _STORE = Store()
    return _STORE


def rulebook():
    global _RULEBOOK
    if _RULEBOOK is None:
        _RULEBOOK = load_rulebook()
    return _RULEBOOK
