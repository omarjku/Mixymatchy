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
