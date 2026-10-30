"""The placeholder renderer and checks of the v2/v3 answer (docs/DECISIONS.md 23, 24): every value is placed by CODE.

v3 (DECISIONS 24): the model call lives in engine/onecall.py (one cached call over the whole fact store); this
module keeps the renderer/allowlist (render), the compact deterministic answer (compact) and the Source chips
(sources).  The history of the v2 writer below explains the checks.

WRITE   one Claude Haiku call with structured output: {"sentence": ..., "facts": [...]}.  The sentence is a
        TEMPLATE: every patient value is a placeholder that references an evidence fact (engine/evidence.py),
        {F3} (the whole statement as the letters word it) or {F3.dose} / {F3.schedule} / {F3.value} / {F3.date} /
        {F3.side} / {F3.name} / {F3.status}.  The model never types a name, number, unit, date, side, dose or
        schedule.  (The first live version used the Citations API; it echoed cited text into the sentence and most
        free-text sentences failed the checks, so values are now placed by reference.)
CHECK   code, deterministic, before display:
          - every placeholder resolves to an existing fact and field; at least one placeholder
          - a field placeholder ({F3.dose}) follows its own fact ({F3} or {F3.name}) in the same clause, with no
            other fact named in between: a dose, schedule, value, date or side can never move to another fact
          - the connector text (the sentence without placeholders) holds only allowed glue words: no digits, no
            negations, advice, hedges, time words, drug classes or markup
          - every REQUIRED fact (the rules' answers of a matched task bundle) is placed
          - at most 2 sentences and MAX_CHARS characters after substitution; repeated words ("HbA1c HbA1c 6.4%")
            collapsed
        Any failure, timeout, no key, budget stop -> the deterministic compact answer (engine/answers.py
        templates of the required / top needs, each citing its facts).  No second model call: the whole v2 path
        has a hard deadline (SECOND_LOOK_V2_DEADLINE, 5 s).
"""
from __future__ import annotations

import re
import unicodedata

from . import answers as A

MAX_SENTENCES = 2
MAX_CHARS = 650  # a matched task bundle can need 4-6 facts (official case 4: ~470 characters expected)
COMPACT_CHARS = 300
FIELDS = ("text", "name", "dose", "schedule", "value", "date", "side", "status")
IDENTIFY = ("text", "name")
CONNECTORS = set("""
the a an of in on at to for from by as and or also both her she it its this these is was were are has had
takes taking documented recorded listed dated latest last most recent with plus which whose value values date
dose doses schedule patient
""".split())
_PH = re.compile(r"\{(F\d+)(?:\.([a-z]+))?\}")
_WORD = re.compile(r"[^\W\d_][\w'’-]*", re.U)
_BAD = re.compile(r"[<>`*#\[\]]|https?:|www\.|\d", re.I)
_SENT_RX = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ\"(])")


def sentences(text):
    out = []
    for s in _SENT_RX.split((text or "").strip()):
        if out and re.search(r"(?:\b[a-z]\.){1,3}$|\b(?:dr|e\.g|i\.e|vs|approx|ca)\.$", out[-1], re.I):
            out[-1] += " " + s  # 's.c. 1-0-1', 'Dr. ...': not a sentence end
        elif s.strip():
            out.append(s.strip())
    return out


# ----------------------------------------------------------------- render + check

def _dedupe(text):
    """'HbA1c HbA1c 6.4%' / 'HbA1c is HbA1c 6.4%' -> 'HbA1c 6.4%' (a label the model wrote before the placeholder)."""
    return re.sub(r"\b((?:[\w%/+().-]+\s+){0,3}?[\w%/+().-]+)\s+(?:(?:is|was)\s+)?\1\b", r"\1", text)


def render(sentence, chunks_by_id, required=(), max_chars=None):
    """Model template -> (ok, why, blocks [{"text", "chunks"}], used fact ids).  Never raises."""
    if not isinstance(sentence, str) or not sentence.strip():
        return False, "empty sentence", [], []
    if any(unicodedata.category(ch) in ("Cf", "Co", "Cs") for ch in sentence):
        return False, "invisible characters", [], []
    phs = list(_PH.finditer(sentence))
    if not phs:
        return False, "no fact placed", [], []
    glue = _PH.sub(" ", sentence)
    if _BAD.search(glue) or "{" in glue or "}" in glue:
        return False, "values or markup typed outside the facts: '%s'" % glue.strip()[:60], [], []
    bad = [w for w in (x.lower().strip("'’-") for x in _WORD.findall(glue)) if w and w not in CONNECTORS]
    if bad:
        return False, "words not allowed outside the facts: %s" % ", ".join(sorted(set(bad))[:5]), [], []
    blocks, used, last_fact, pos = [], [], None, 0
    for m in phs:
        fid, field = m.group(1), m.group(2) or "text"
        c = chunks_by_id.get(fid)
        if c is None or field not in FIELDS or not c["fields"].get(field):
            return False, "unknown fact or field {%s%s}" % (fid, "." + field if m.group(2) else ""), [], []
        between = sentence[pos:m.start()]
        if re.search(r"[;.]", between):
            last_fact = None  # a new clause: a field must name its own fact again
        if field not in IDENTIFY and last_fact != fid:
            return False, "{%s.%s} is not next to its own fact" % (fid, field), [], []
        if field in IDENTIFY:
            last_fact = fid
        blocks.append({"text": between + c["fields"][field], "chunks": [fid]})
        used.append(fid)
        pos = m.end()
    blocks.append({"text": sentence[pos:], "chunks": []})
    missing = [r for r in required if r not in used]
    if missing:
        return False, "required facts left out: %s" % ", ".join(missing[:5]), [], []
    for b in blocks:
        b["text"] = _dedupe(b["text"])
    text = "".join(b["text"] for b in blocks)
    text = re.sub(r"\s+([,.;:)])", r"\1", " ".join(text.split()))
    if len(text) > (max_chars or MAX_CHARS):
        return False, "too long (%d characters)" % len(text), [], []
    if len(sentences(text)) > MAX_SENTENCES:
        return False, "more than %d sentences" % MAX_SENTENCES, [], []
    blocks = [b for b in blocks if b["text"].strip() or b["chunks"]]
    if blocks:
        blocks[0]["text"] = blocks[0]["text"].lstrip()
        blocks[0]["text"] = blocks[0]["text"][:1].upper() + blocks[0]["text"][1:]
    return True, None, blocks, list(dict.fromkeys(used))


# ----------------------------------------------------------------- the compact deterministic answer

def compact(st, k, ranked, chunks_by_id):
    """Templates (engine/answers.py) of the required needs (a matched task bundle's answers), else the top 1-2
    needs; the first is sentence 1, the rest sentence 2 (joined with ';'); each block cites its own facts."""
    req = [(n, ids) for n, ids in ranked if n.get("required")]
    pick = req or ranked[:2]
    blocks, total = [], 0
    for n, ids in pick:
        t = A.template(st, k, n).strip().rstrip(".")
        if blocks and not req and total + len(t) > COMPACT_CHARS:
            break
        if len(blocks) == 0:
            sep = ""
        elif len(blocks) == 1:
            sep, t = ". ", A._cap(t)
        else:
            sep, t = "; ", t if t.split(" ")[0].rstrip(":") in A.MONTHS else A._low(t)
        blocks.append({"text": sep + t, "chunks": [i for i in ids if i in chunks_by_id]})
        total += len(sep) + len(t)
    if blocks:
        blocks[-1]["text"] += "."
    return blocks


def sources(blocks, chunks_by_id):
    """The Source chips: one per placed fact, in order of first use."""
    out, seen = [], set()
    for bl in blocks:
        for cid in bl.get("chunks") or []:
            c = chunks_by_id.get(cid)
            if c and cid not in seen and c.get("passages"):
                seen.add(cid)
                out.append({"chunk": cid, "kind": c["kind"], "label": c["text"].split(":")[0][:60],
                            "passages": list(c["passages"]), "facts": list(c.get("facts") or [])})
    return out


# ----------------------------------------------------------------- v3.1: concepts, contradiction flags, one sentence
# (docs/DECISIONS.md 24, v3.1).  All code-written text below is fixed wording or the facts' own words.

_CONCEPT_DROP = {"known", "well", "controlled", "at", "last", "examination", "the", "a", "an", "of", "diagnosis"}
_SIDES = ("left", "right")
_CONTRA = {}


def concept(f):
    """A store fact -> its concept key: the same drug + dose, the same value (+ side), or the same normalised label.
    'Contrast media allergy (nausea, vomiting) at last examination' == 'Known contrast media allergy'."""
    a = f.get("attrs") or {}
    cat = f.get("category") or "-"
    if a.get("generic"):
        return (cat, "drug", str(a["generic"]).lower(), str(a.get("dose") or a.get("amount") or ""))
    if a.get("value") not in (None, ""):
        return (cat, "value", str(a["value"]), str(a.get("unit") or ""), str(a.get("side") or ""))
    from .understand import fold
    lab = re.sub(r"\([^)]*\)", " ", fold(str(f.get("label_en") or "")).lower())
    words = [w for w in re.findall(r"[a-z0-9]+", lab) if w not in _CONCEPT_DROP]
    return (cat, "label", " ".join(words))


def text_concept(text):
    from .understand import fold
    lab = re.sub(r"\([^)]*\)", " ", fold(str(text or "")).lower())
    return ("text", " ".join(w for w in re.findall(r"[a-z0-9]+", lab) if w not in _CONCEPT_DROP))


def contradictions(st):
    """Counted contradictions (compare/, engine/conflicts.py) -> {store fact id 'f0102': [entry]}; an entry holds
    the kind, the title and what the flag needs (sides with their letters, other dates)."""
    key = id(st)
    if key in _CONTRA:
        return _CONTRA[key]
    from .screen import _contradictions
    idx = {}
    for c in _contradictions(st)[0] or []:
        if not c.get("counted", True):
            continue
        claims = [cl for cl in c.get("claims") or [] if cl.get("fact_id")]
        e = {"id": c.get("id"), "kind": c.get("kind"), "title": c.get("title_en") or c.get("summary_en") or "",
             "sides": {}, "structure_of": {}, "dates": {}, "majority": {}}
        if c.get("kind") == "laterality":
            for cl in claims:
                m = re.match(r"\s*([\w ]+?):\s*(left|right)\b", str(cl.get("asserted") or ""), re.I)
                if m:
                    s = m.group(1).strip()
                    e["structure_of"][cl["fact_id"]] = (s, m.group(2).lower())
                    e["sides"].setdefault(s, {}).setdefault(m.group(2).lower(), set()).add(cl.get("doc_id"))
            for s, by_side in e["sides"].items():
                n = {side: sum(1 for cl in claims if e["structure_of"].get(cl["fact_id"]) == (s, side))
                     for side in by_side}
                top = sorted(n.items(), key=lambda x: -x[1])
                if len(top) > 1 and top[0][1] > top[1][1]:
                    e["majority"][s] = top[0][0]
        for cl in claims:
            d = re.search(r"(\d{4}-\d{2}-\d{2})", str(cl.get("asserted") or ""))
            if d:
                e["dates"][cl["fact_id"]] = d.group(1)
        for cl in claims:
            idx.setdefault(cl["fact_id"], [])
            if e not in idx[cl["fact_id"]]:
                idx[cl["fact_id"]].append(e)
    _CONTRA[key] = idx
    return idx


def minority(st, store_id):
    """A fact on the minority side of a counted laterality contradiction -> the majority side's facts (newest first)
    of the same structure; else None.  The answer may not show the minority side alone (DECISIONS 24, v3.1)."""
    for e in contradictions(st).get(store_id) or []:
        s_side = e["structure_of"].get(store_id)
        if not s_side or e["majority"].get(s_side[0]) in (None, s_side[1]):
            continue
        want = (s_side[0], e["majority"][s_side[0]])
        maj = [f for f, ss in e["structure_of"].items() if ss == want and f in st.fact_by_id]
        return sorted(maj, key=lambda f: (str(st.fact_by_id[f].get("date") or ""), f), reverse=True)
    return None


def _n_letters(n):
    return "one letter says" if n == 1 else "%d letters say" % n


def flag_for(e, text, store_id=None):
    """The flag of one contradiction for a text that states one side of it."""
    if e["kind"] == "laterality":
        side = None
        if store_id and store_id in e["structure_of"]:
            s, side = e["structure_of"][store_id]
            by = e["sides"].get(s) or {}
        else:
            by = next(iter(e["sides"].values()), {})
        if side is None:
            m = re.search(r"\b(left|right)\b", text or "", re.I)
            side = m.group(1).lower() if m else None
        other = [(sd, docs) for sd, docs in by.items() if sd != side]
        if side and other:
            sd, docs = other[0]
            return side, "(%s %s)" % (_n_letters(len(docs)), sd)
        return None, "(the letters disagree on the side)"
    if e["kind"] == "bmi_mismatch":
        if re.search(r"\bBMI\b", text or ""):
            return None, "(BMI does not match weight and height)"
        return None, "(BMI mismatch)"
    if e["kind"] == "event_date" and store_id in e["dates"]:
        own = e["dates"][store_id]
        others = sorted({d for d in e["dates"].values() if d != own})
        if others:
            from . import answers as A
            return None, "(the letters also give %s)" % " or ".join(A.fmt_date(d, "day") for d in others)
    return None, "(the letters disagree)"


def flag_text(text, entries, store_id=None, whole=None):
    """Insert each entry's flag into text (after the side word for a laterality contradiction), once.  A flag the
    answer already states (whole: the answer's text, e.g. a template's 'one letter ... says right') is not repeated."""
    orig = text
    shown = set()
    for e in entries:
        side, fl = flag_for(e, orig, store_id)
        if fl in text or fl in shown or fl in (whole or ""):
            continue
        if e["kind"] == "laterality" and side and re.search(
                r"(?i)\bsays? (%s)\b" % "|".join(x for x in _SIDES if x != side), whole or text):
            continue
        shown.add(fl)
        m = re.search(r"\b%s\b" % side, text, re.I) if side else None
        if m:
            text = text[:m.end()] + " " + fl + text[m.end():]
        else:
            stripped = text.rstrip()
            tail = ""
            while stripped and stripped[-1] in ".;,":
                tail, stripped = stripped[-1] + tail, stripped[:-1]
            text = stripped + " " + fl + tail + text[len(text.rstrip()):]
    return text


def flag_blocks(st, blocks, chunks_by_id):
    """Every cited fact in a counted contradiction shows its flag in the answer (never the fact alone).
    -> (blocks, titles of the contradictions shown)."""
    idx = contradictions(st)
    whole = "".join(b.get("text") or "" for b in blocks)
    titles = []
    out = []
    done = set()
    for b in blocks:
        b = dict(b)
        for cid in b.get("chunks") or []:
            if cid in done:  # a field placeholder of a fact already flagged ({F1.date} after {F1})
                continue
            done.add(cid)
            c = chunks_by_id.get(cid) or {}
            facts = [f for f in c.get("facts") or [] if f in idx]
            if not facts:
                continue
            if c.get("kind") not in (None, "fact"):
                continue  # computed / status lines state their own basis ("the side most letters document")
            # the fact whose wording the block shows (the first one; an item groups the same statement)
            fid = facts[0]
            if len(c.get("facts") or []) > 1:  # a grouped item: the side the text states decides the flag
                fid = None
            ents = [e for f in facts for e in idx[f]]
            ents = list({e["id"]: e for e in ents}.values())
            b["text"] = flag_text(b["text"], ents, fid, whole)
            titles += [e["title"] for e in ents]
        out.append(b)
    return out, list(dict.fromkeys(t for t in titles if t))


# ---- one natural sentence from fact items (the list form is only the fallback)

DRUG_CATS = {"antithrombotic", "glucose_lowering", "antihypertensive", "lipid_lowering", "nitrate", "vitamin",
             "bone_agent", "therapy"}
HAS_CATS = {"diagnosis", "allergy", "carotid_stenosis", "carotid_plaque", "carotid_bruit", "histology"}


def group_of(f):
    """'takes' (a drug), 'has' (a condition the letters state), 'doc' (anything else)."""
    a = f.get("attrs") or {}
    lab = str(f.get("label_en") or "")
    if f.get("category") in DRUG_CATS and (a.get("dose") or a.get("schedule") or a.get("generic")):
        return "takes"
    if f.get("category") in HAS_CATS and a.get("assertion", "positive") == "positive" and not re.match(
            r"(?i)(?:(?:no|not|question|suspected)\b|diagnosis:)", lab):
        return "has"
    return "doc"


def _and(parts):
    parts = [p for p in parts if p]
    if len(parts) <= 2:
        return [(" and " if i else "", p) for i, p in enumerate(parts)]
    return [("" if i == 0 else (" and " if i == len(parts) - 1 else ", "), p) for i, p in enumerate(parts)]


_DATE_TAIL = re.compile(r" \((\d{1,2} [A-Z][a-z]+ \d{4}|[A-Z][a-z]+ \d{4})\)$")


def natural(items, start=True):
    """[{"text", "chunks", "group"}] -> blocks of one sentence (no final period):
    'She takes A and B and has C; also documented: D and E' (+ 'raw' items, e.g. computed lines, after ';')."""
    from . import answers as A
    groups = {"takes": [], "has": [], "doc": [], "raw": []}
    for it in items:
        g = it.get("group") if it.get("group") in groups else "doc"
        if g == "raw" and not re.match(r"(?i)(no|not)\b", it["text"].strip()):
            g = "doc"  # a computed value ("change -12 kg over 10 months") is listed; an absence stays its own clause
        groups[g].append(it)
    blocks = []

    def add(prefix, its, low=True):
        texts = [it["text"].strip().rstrip(".") for it in its]
        for j in range(len(texts) - 1):  # a run of items with the same date: the date once, after the last
            m, n = _DATE_TAIL.search(texts[j]), _DATE_TAIL.search(texts[j + 1])
            if m and n and m.group(1) == n.group(1):
                texts[j] = texts[j][:m.start()]
        for j, (sep, t) in enumerate(_and(texts)):
            it = its[j]
            t = A._low(t) if low else t
            blocks.append({"text": (prefix if j == 0 else "") + sep + t, "chunks": list(it.get("chunks") or [])})
    subj = False
    if groups["takes"]:
        add("she takes ", groups["takes"])
        subj = True
    if groups["has"]:
        add(" and has " if subj else "she has ", groups["has"])
        subj = True
    if groups["doc"]:
        add("; also documented: " if subj else "", groups["doc"], low=subj)
    for it in groups["raw"]:
        t = it["text"].strip().rstrip(".")
        blocks.append({"text": ("; " + A._low(t)) if blocks else t, "chunks": list(it.get("chunks") or [])})
    if blocks and start:
        blocks[0]["text"] = A._cap(blocks[0]["text"].lstrip())
    return blocks
