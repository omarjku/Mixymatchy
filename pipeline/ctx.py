"""Document context: dates, stays, passage lookup, fact construction helpers."""
import os
import re

from .common import DOC_DIR, SLASH_DATE_RE, display_text, find_dates, iso, load_json, norm_ws
from .passages import build_passages

GENERIC_HEADINGS = {"zusammenfassung", "befundzusammenfassung", "gesamtbeurteilung", "interpretation",
                    "befunde", "erhobene befunde"}
HEADER_DATE_RE = re.compile(r"\bam\s+(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)")
STAY_RE = re.compile(r"Aufnahme am\s+(\d{1,2})/(\d{1,2})/(\d+)\s*\|\s*Entlassen am\s+(\d{1,2})/(\d{1,2})/(\d+)")
ENCOUNTER_RE = re.compile(r"welche am\s+(\d{1,2})\.(\d{1,2})\.(\d{4})\b[^.]*\bBehandlung")
MED_SECTION_RE = re.compile(r"^(entlassungs)?medikation", re.I)


class Doc:
    def __init__(self, doc_id, raw):
        self.id = doc_id
        meta = raw.get("metadata", {})
        self.meta = meta
        self.text = display_text(raw["text"])
        self.title = meta.get("title")
        self.type = meta.get("type")
        # document date: first "am dd.mm.yyyy" in the first lines of the text, fallback metadata
        head = "\n".join(self.text.split("\n")[:16])
        m = HEADER_DATE_RE.search(head)
        self.date = iso(*m.groups()) if m else None
        if not self.date:
            self.date = meta.get("date")
        self.date_source = "text" if m else "metadata"
        self.stay_admission = self.stay_discharge = None
        sm = STAY_RE.search(self.text)
        if sm:
            a = sm.groups()
            self.stay_admission = iso(a[0], a[1], a[2]) if len(a[2]) == 4 else None
            self.stay_discharge = iso(a[3], a[4], a[5]) if len(a[5]) == 4 else None
        em = ENCOUNTER_RE.search(self.text)
        self.encounter_date = iso(*em.groups()) if em else None
        self.passages = build_passages(doc_id, self.text)
        # parent (non-generic) heading per passage, for dating
        parent = None
        self.parent_section = {}
        for p in self.passages:
            sec = p["section"]
            if sec and p["text"] == sec:
                if sec.lower().rstrip(":").strip() not in GENERIC_HEADINGS:
                    parent = sec
            self.parent_section[p["id"]] = parent
        self.has_med_list = any(p["kind"] == "table_row" for p in self.passages)

    @property
    def year(self):
        return int(self.date[:4]) if self.date else None

    def clinical_date(self):
        """Default date for findings in this document: discharge (stay) > encounter > document date."""
        return self.stay_discharge or self.encounter_date or self.date


def load_docs():
    docs = {}
    for f in sorted(os.listdir(DOC_DIR)):
        if f.endswith(".json"):
            did = f[:-5]
            docs[did] = Doc(did, load_json(os.path.join(DOC_DIR, f)))
    return docs


class Context:
    def __init__(self, docs):
        self.docs = docs
        self.pid = {p["id"]: p for d in docs.values() for p in d.passages}
        self.latest_year = max(d.year for d in docs.values())
        med_docs = [d for d in docs.values() if d.has_med_list]
        self.latest_med_doc = max(med_docs, key=lambda d: d.date).id if med_docs else None

    def section_date(self, p):
        doc = self.docs[p["doc_id"]]
        for sec in (p["section"], doc.parent_section.get(p["id"])):
            if sec:
                ds = find_dates(sec)
                if ds:
                    return ds[0][0]
        return None

    def date_for(self, p, quote=None, explicit=False):
        """Return (date, precision)."""
        doc = self.docs[p["doc_id"]]
        sd = self.section_date(p)
        if explicit:
            if quote:
                ds = find_dates(quote)
                if ds:
                    return ds[0][0], "day"
            ds = {d for d, _, _ in find_dates(p["text"])}
            if len(ds) == 1:
                return ds.pop(), "day"
            mm = re.search(r"(?:Anfang|Mitte|Ende)\s+(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+(\d{4})", p["text"])
            if mm:
                from .common import MONTHS_DE
                return "%s-%02d-01" % (mm.group(2), MONTHS_DE[mm.group(1).lower()]), "month"
        if sd:
            return sd, "day"
        return doc.clinical_date(), "day"

    def era_status(self, p):
        return "current" if self.docs[p["doc_id"]].year == self.latest_year else "historical"

    def med_status(self, p):
        if p["doc_id"] == self.latest_med_doc and p["section"] and MED_SECTION_RE.match(p["section"]):
            return "current"
        return "historical"


def quote_span(text, s, e, maxlen=220):
    """Quote = whole passage when short, else the clause around [s, e)."""
    if len(text) <= maxlen:
        return 0, len(text)
    # parentheses enclosing the match
    lo = text.rfind("(", 0, s)
    if lo != -1 and text.find(")", lo) >= e and text.find(")", lo) != -1:
        hi = text.find(")", lo)
        if hi - lo < maxlen:
            return lo + 1, hi
    a = max(text.rfind(";", 0, s), text.rfind(". ", 0, s))
    a = 0 if a == -1 else a + 1
    b_candidates = [i for i in (text.find(";", e), text.find(". ", e)) if i != -1]
    b = min(b_candidates) if b_candidates else len(text)
    while a < s and text[a].isspace():
        a += 1
    return a, max(b, e)


def fact(p, quote, ips, category, label, attrs=None, status="unknown", date=None, precision="day",
         code=None, origin="rule"):
    attrs = {k: v for k, v in (attrs or {}).items() if v not in (None, "", [], {})}
    return {
        "ips_section": ips,
        "category": category,
        "code": code,
        "label_en": norm_ws(label),
        "attrs": attrs,
        "date": date,
        "date_precision": precision,
        "status": status,
        "quote": quote,
        "passage_ids": [p["id"]],
        "origin": origin,
        "verified": False,
    }
