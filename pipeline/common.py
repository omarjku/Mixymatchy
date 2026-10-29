"""Shared helpers: paths, document loading, dates, whitespace-tolerant search, number checks."""
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATIENT_DIR = os.path.join(ROOT, "data", "patient-0000-0001")
DOC_DIR = os.path.join(PATIENT_DIR, "documents")
BUILD_DIR = os.path.join(ROOT, "data", "build")

DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{4})(?!\d)")
MONTHS_DE = {"januar": 1, "jänner": 1, "februar": 2, "märz": 3, "april": 4, "mai": 5, "juni": 6,
             "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "dezember": 12}
DATE_LONG_RE = re.compile(r"(?<!\d)(\d{1,2})\.\s*(" + "|".join(MONTHS_DE) + r")\s+(\d{4})(?!\d)", re.I)
SLASH_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)")


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def display_text(raw):
    """Contract: <BR> replaced BEFORE unescaping."""
    return html.unescape(raw.replace("<BR>", "\n"))


def iso(d, m, y):
    try:
        d, m, y = int(d), int(m), int(y)
    except ValueError:
        return None
    if not (1 <= d <= 31 and 1 <= m <= 12 and 1900 <= y <= 2100):
        return None
    return "%04d-%02d-%02d" % (y, m, d)


def find_dates(text):
    """All explicit day-precision dates in text, as (iso, start, end)."""
    out = []
    for m in DATE_RE.finditer(text):
        v = iso(m.group(1), m.group(2), m.group(3))
        if v:
            out.append((v, m.start(), m.end()))
    for m in DATE_LONG_RE.finditer(text):
        v = iso(m.group(1), MONTHS_DE[m.group(2).lower()], m.group(3))
        if v:
            out.append((v, m.start(), m.end()))
    return sorted(out, key=lambda x: x[1])


def clean_ibm_text(s):
    """Strip <SPAN ...> markup, unescape entities, normalise whitespace."""
    s = re.sub(r"<[^<>]*>", "", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def ws_pattern(needle):
    toks = needle.split()
    if not toks:
        return None
    return re.compile(r"\s+".join(re.escape(t) for t in toks))


def find_ws(hay, needle, start=0):
    """Whitespace-tolerant exact search. Returns (start, end) in hay or None."""
    pat = ws_pattern(needle)
    if pat is None:
        return None
    m = pat.search(hay, start)
    return (m.start(), m.end()) if m else None


def norm_ws(s):
    return re.sub(r"\s+", " ", s).strip()


NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")


def numbers_in(obj):
    """Numbers in a label/attrs value (recursively)."""
    if obj is None or isinstance(obj, bool):
        return []
    if isinstance(obj, (int, float)):
        return [str(obj)]
    if isinstance(obj, str):
        return NUM_RE.findall(obj)
    if isinstance(obj, (list, tuple)):
        return [n for x in obj for n in numbers_in(x)]
    if isinstance(obj, dict):
        return [n for v in obj.values() for n in numbers_in(v)]
    return []


def number_in_quote(num, quote):
    q = quote.replace(",", ".")
    n = num.replace(",", ".")
    if re.search(r"(?<!\d)" + re.escape(n) + r"(?!\d)", q):
        return True
    # "6.40" vs "6.4" style trailing zeros are not expected; integers written as "16.0" etc.
    if "." in n:
        try:
            f = float(n)
            if f == int(f) and re.search(r"(?<!\d)" + str(int(f)) + r"(?!\d)", q):
                return True
        except ValueError:
            pass
    return False
