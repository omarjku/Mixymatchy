"""Passage index: lines, medication-table rows and sentences with their nearest section heading."""
import re

# Headings that appear without a trailing colon.
BARE_HEADINGS = {
    "gesamtbeurteilung", "befundzusammenfassung", "langzeit-ekg", "24h-rr-messung",
    "radiologischer befund", "histopathologischer befund", "ambulanter patientenbrief",
    "konsil für augenheilkunde", "laborbefund", "zusammenfassung",
}
CLOSING_RE = re.compile(r"^(mit (freundlichen|kollegialen) grüßen)", re.I)
MED_SECTION_RE = re.compile(r"^(entlassungs)?medikation\b", re.I)
TABLE_HEADER_RE = re.compile(r"^applikation\b.*\bmo\b.*\bmi\b.*\bab\b.*\bna\b", re.I)

# German abbreviations after which a period does not end a sentence.
ABBREV = {
    "pat", "li", "re", "bds", "z.b", "st.p", "z.n", "vd.a", "v.a", "ca", "dr", "prim", "wg", "ggf",
    "bzw", "inkl", "art", "diab", "mell", "ventr", "max", "kalk", "systol", "tabl", "gem", "s.c",
    "i.v", "p.o", "u.a", "d.h", "sin", "dext", "std", "nr", "abt", "vs", "evtl", "oa", "usw",
    "geb", "zn", "stp", "lt", "insb", "mind", "ca", "sek", "min", "re.", "li.", "a", "v",
}
SENT_END_RE = re.compile(r"([.!?]+)(\s+)(?=[A-ZÄÖÜ0-9(\"„])")
LABEL_START_RE = re.compile(r"[A-ZÄÖÜ][\wäöüß-]*:")
SPLIT_MIN_LEN = 100


def is_heading(line):
    s = line.strip()
    if not s or len(s) > 70:
        return False
    if s.lower().rstrip(":") in BARE_HEADINGS:
        return True
    if s.endswith(":") and s.count(":") >= 1:
        body = s[:-1]
        if ":" in body:
            return False
        words = body.split()
        return 1 <= len(words) <= 8
    return False


def split_sentences(text):
    """Return list of (start, end) spans of sentences inside text."""
    spans = []
    cur = 0
    for m in SENT_END_RE.finditer(text):
        end = m.end(1)
        # token before the period
        before = text[cur:m.start(1)]
        tok = re.split(r"[\s(]", before)[-1] if before else ""
        tok_l = tok.lower().strip(".")
        punct = m.group(1)
        if punct.startswith(".") and len(punct) == 1:
            if tok_l in ABBREV or re.fullmatch(r"\d+", tok_l) or re.fullmatch(r"[a-zäöü]", tok_l):
                # abbreviation: only split if next token is a "Label:" (e.g. "bds. Therapie:")
                if not LABEL_START_RE.match(text, m.end()):
                    continue
        spans.append((cur, end))
        cur = m.end()
    spans.append((cur, len(text)))
    out = []
    for s, e in spans:
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        if e > s:
            out.append((s, e))
    return out


def build_passages(doc_id, text):
    passages = []
    section = None
    in_table = False
    pos = 0
    n = 0

    def add(kind, s, e, sec):
        nonlocal n
        passages.append({
            "id": "%s:p%04d" % (doc_id, n),
            "doc_id": doc_id,
            "section": sec,
            "kind": kind,
            "start": s,
            "end": e,
            "text": text[s:e],
        })
        n += 1

    for raw_line in text.split("\n"):
        ls = pos
        le = pos + len(raw_line)
        pos = le + 1
        s, e = ls, le
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        if s == e:
            continue
        line = text[s:e]
        if CLOSING_RE.match(line):
            in_table = False
            section = None
            add("line", s, e, None)
            continue
        if is_heading(line):
            section = line
            in_table = bool(MED_SECTION_RE.match(line))
            add("line", s, e, section)
            continue
        if in_table:
            if TABLE_HEADER_RE.match(line):
                add("line", s, e, section)
            elif re.search(r"\d", line) or re.search(r"\b(oral|s\.c\.|i\.v\.|Tropfen|Tabl)\b", line):
                add("table_row", s, e, section)
            else:
                in_table = False
                add("line", s, e, section)
            continue
        spans = split_sentences(line) if len(line) > SPLIT_MIN_LEN else [(0, len(line))]
        if len(spans) <= 1:
            add("line", s, e, section)
        else:
            for a, b in spans:
                add("sentence", s + a, s + b, section)
    for p in passages:
        assert text[p["start"]:p["end"]] == p["text"], p["id"]
    return passages
