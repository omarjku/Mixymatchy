"""Step A1–A2: load the documents, normalise the text and split it into numbered segments.

Every fact and finding links to a segment ID, so these IDs must stay stable:
re-running ingest on the same documents gives the same IDs.
"""
import html
import json
import re

from .config import PATIENT_DIR
from .schema import Document, Segment

# Abbreviations that end with "." but do not end a sentence.
ABBREV = {"dr", "geb", "li", "re", "st", "p", "z", "n", "v", "a", "bds", "ca", "vd", "zn", "mo", "mi",
          "ab", "na", "pat", "art", "diab", "mell", "sin", "dex", "ggf", "bzw", "evtl", "inkl", "prim", "oa"}
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ0-9])")
HEADING = re.compile(r"^[A-ZÄÖÜa-zäöü0-9 .\-/()+]{2,60}:$")
TABLE_SECTIONS = {"Entlassungsmedikation"}


def normalise(raw: str) -> str:
    text = html.unescape(raw).replace("<BR>", "\n").replace("\r", "")
    return "\n".join(line.rstrip() for line in text.split("\n"))


def load_documents() -> list[Document]:
    index = json.loads((PATIENT_DIR / "documents.json").read_text(encoding="utf-8"))["documents"]
    docs = []
    for meta in index:
        raw = json.loads((PATIENT_DIR / "documents" / f"{meta['id']}.json").read_text(encoding="utf-8"))
        docs.append(Document(id=meta["id"], title=meta["title"], date=meta["date"], type=meta["type"],
                             department=meta.get("department", ""), text=normalise(raw["text"])))
    return sorted(docs, key=lambda d: d.date)


def _split_sentences(line: str) -> list[tuple[int, int]]:
    """Return (start, end) spans within a line, avoiding splits after abbreviations."""
    spans, start = [], 0
    for m in SENTENCE_END.finditer(line):
        prev_word = re.findall(r"([A-Za-zÄÖÜäöü]+)\.$", line[start:m.start()])
        if prev_word and prev_word[0].lower() in ABBREV:
            continue
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(line)))
    return spans


def segment(doc: Document) -> list[Segment]:
    segments, section, pos, n = [], None, 0, 0
    for line in doc.text.split("\n"):
        line_start, pos = pos, pos + len(line) + 1
        stripped = line.strip()
        if not stripped:
            continue
        offset = line_start + (len(line) - len(line.lstrip()))
        if stripped.startswith("Mit freundlichen") or stripped.startswith("Mit kollegialen"):
            section = "Signatur"  # closing formula ends the medication table
        if HEADING.match(stripped):
            section = stripped[:-1].strip()
            kind_spans = [("heading", 0, len(stripped))]
        elif section in TABLE_SECTIONS and not stripped.startswith(("Applikation", "Mit freundlichen")):
            kind_spans = [("table_row", 0, len(stripped))]
        else:
            kind_spans = [("sentence", s, e) for s, e in _split_sentences(stripped)]
        for kind, s, e in kind_spans:
            text = stripped[s:e].strip()
            if not text:
                continue
            n += 1
            start = offset + s + (len(stripped[s:e]) - len(stripped[s:e].lstrip()))
            segments.append(Segment(id=f"{doc.id}:s{n:03d}", doc_id=doc.id, kind=kind, section=section,
                                    text=text, start=start, end=start + len(text), doc_date=doc.date))
    return segments


def ingest() -> tuple[list[Document], list[Segment]]:
    docs = load_documents()
    segs = [s for d in docs for s in segment(d)]
    by_id = {d.id: d for d in docs}
    for s in segs:  # offsets must always point at exactly the segment text
        assert by_id[s.doc_id].text[s.start:s.end] == s.text, s.id
    return docs, segs
