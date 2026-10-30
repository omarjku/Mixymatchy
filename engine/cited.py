"""v2 steps 4-5 (docs/DECISIONS.md 23): a 1-2 sentence answer whose every value is placed by CODE.

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

import json
import os
import re
import time
import unicodedata
from concurrent.futures import TimeoutError as FutureTimeout

from . import answers as A
from . import llm, llm_budget

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


def render(sentence, chunks_by_id, required=()):
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
    if len(text) > MAX_CHARS:
        return False, "too long (%d characters)" % len(text), [], []
    if len(sentences(text)) > MAX_SENTENCES:
        return False, "more than %d sentences" % MAX_SENTENCES, [], []
    blocks = [b for b in blocks if b["text"].strip() or b["chunks"]]
    if blocks:
        blocks[0]["text"] = blocks[0]["text"].lstrip()
        blocks[0]["text"] = blocks[0]["text"][:1].upper() + blocks[0]["text"][1:]
    return True, None, blocks, list(dict.fromkeys(used))


# ----------------------------------------------------------------- the writer (structured output)

STYLE = (
    "You are the answer writer of Second Eye. A clinician asked about ONE patient. Answer in ONE sentence, two "
    "at most, in English, using only the numbered facts (taken from the patient's letters).\n"
    "Write every patient value as a placeholder, never as text: {F3} places the whole fact as the letters word it; "
    "{F3.name}, {F3.dose}, {F3.schedule}, {F3.value}, {F3.date}, {F3.side}, {F3.status} place one field (only "
    "fields listed for that fact), and only right after {F3} or {F3.name} of the same fact. Do not write a fact's "
    "name before its placeholder ('HbA1c {F5}' is wrong; write '{F5}').\n"
    "Between placeholders you may write only these words: " + ", ".join(sorted(CONNECTORS)) + ", and punctuation "
    "(, ; : . ( ) -). No numbers, no other words: no advice, no interpretation, no negation, no causes.\n"
    "Place every fact listed as REQUIRED. Then add only what the question itself needs. If the question asks for "
    "something only a 'not documented' fact covers, place that fact. List the facts you placed in 'facts'."
)
SCHEMA = {
    "type": "object",
    "properties": {"sentence": {"type": "string"}, "facts": {"type": "array", "items": {"type": "string"}}},
    "required": ["sentence", "facts"], "additionalProperties": False,
}


def _fact_line(c):
    f = c["fields"]
    extra = "; ".join("%s=%s" % (k, f[k]) for k in FIELDS if k != "text" and f.get(k))
    return "%s [%s] %s%s" % (c["id"], c["kind"], f["text"], (" | " + extra) if extra else "")


def writer_params(question, chunks, required):
    facts = "\n".join(_fact_line(c) for c in chunks)
    return dict(
        model=llm.model(),
        max_tokens=300,
        thinking={"type": "disabled"},  # Haiku 5.5: allowed at effort <= high
        system=[{"type": "text", "text": STYLE, "cache_control": {"type": "ephemeral"}}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": "Question: %s\nREQUIRED: %s\nFacts:\n%s" % (
            " ".join(str(question or "").split())[:600], ", ".join(required) or "none", facts)}],
    )


def _get(x, name, default=None):
    return x.get(name, default) if isinstance(x, dict) else getattr(x, name, default)


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


# ----------------------------------------------------------------- the whole step

def _timeout(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return float(default)


def deadline_s():
    return _timeout("SECOND_LOOK_V2_DEADLINE", "5.0")


def _cache_key(question, chunks, required):
    return ("answer_v2", llm.model(), " ".join(str(question or "").lower().split()),
            tuple(c["text"] for c in chunks), tuple(required))


_writer_hook = None  # eval without a key: fn(question, chunks, required, compact blocks) -> {"sentence", "facts"}


def set_writer(fn):
    global _writer_hook
    _writer_hook = fn


def writer_available(use_llm):
    return _writer_hook is not None or (use_llm and llm.available()
                                        and os.environ.get("SECOND_LOOK_ANSWERS_LLM", "1") != "0")


def _write(question, chunks, required, timeout, stats, fallback):
    """-> {"sentence", "facts"} or None (stats records why)."""
    if _writer_hook is not None:
        stats["called"] = True
        return _writer_hook(question, chunks, required, fallback)
    b = llm_budget.budget()
    if not b.reserve():
        stats["skipped"]["writer"] = b.why_blocked() or "budget"
        return None
    stats["called"] = True
    params = writer_params(question, chunks, required)
    fut = llm._pool.submit(llm._call, params)
    t = time.perf_counter()
    try:
        msg = fut.result(timeout=max(0.05, timeout))
    except FutureTimeout:
        b.error()
        stats["skipped"]["writer"] = "timeout"
        return None
    except Exception as e:
        b.error()
        stats["skipped"]["writer"] = "error: %s" % type(e).__name__
        return None
    finally:
        stats["ms"]["writer"] = round((time.perf_counter() - t) * 1000, 1)
    try:
        if _get(msg, "usage") is not None:
            stats["cost_eur"] += b.record(params["model"], msg.usage)
        if _get(msg, "stop_reason") in ("refusal", "max_tokens"):
            stats["skipped"]["writer"] = "stop_reason: %s" % _get(msg, "stop_reason")
            return None
        txt = next((_get(x, "text", "") for x in _get(msg, "content") or [] if _get(x, "type") == "text"), "")
        data = json.loads(txt)
        return data if isinstance(data, dict) else None
    except Exception as e:
        b.error()
        stats["skipped"]["writer"] = "invalid: %s" % type(e).__name__
        return None


def answer(st, k, question, chunks, ranked, use_llm=True, t0=None):
    """-> (answer dict, stats).  answer: {"blocks", "text", "origin" llm|template, "verified"}.
    t0: the request's start (the deadline counts from there)."""
    t0 = t0 if t0 is not None else time.perf_counter()
    by_id = {c["id"]: c for c in chunks}
    stats = {"origin": "template", "called": False, "rejected": [], "skipped": {}, "ms": {}, "cost_eur": 0.0}
    fallback = compact(st, k, ranked, by_id)
    required = [i for n, ids in ranked if n.get("required") for i in ids
                if by_id.get(i, {}).get("kind") in ("fact", "computed", "status")]

    def done(blocks, origin):
        stats["origin"] = origin
        stats["ms"]["total"] = round((time.perf_counter() - t0) * 1000, 1)
        stats["cost_eur"] = round(stats["cost_eur"], 6)
        return {"blocks": blocks, "text": "".join(b["text"] for b in blocks).strip(), "origin": origin,
                "verified": True}, stats

    if not ranked or not chunks:
        stats["skipped"]["writer"] = "no evidence"
        return done(fallback, "template")
    if not writer_available(use_llm):
        stats["skipped"]["writer"] = "disabled" if not llm.enabled() or not use_llm else "no key"
        return done(fallback, "template")
    left = deadline_s() - (time.perf_counter() - t0) - 0.15
    if left < 0.3:
        stats["skipped"]["writer"] = "no time left"
        return done(fallback, "template")
    b = llm_budget.budget()
    key = _cache_key(question, chunks, required)
    hit = b.cache_get(key) if _writer_hook is None else None
    if hit is not None:
        stats["cached"] = True
        return done(hit, "llm")
    out = _write(question, chunks, required, min(_timeout("SECOND_LOOK_V2_WRITER_TIMEOUT", "2.5"), left),
                 stats, [dict(x) for x in fallback])
    if not out:
        return done(fallback, "template")
    ok, why, blocks, _used = render(out.get("sentence"), by_id, required)
    if not ok:
        stats["rejected"].append({"layer": "check", "reasons": [why], "sentence": str(out.get("sentence"))[:300]})
        return done(fallback, "template")
    if _writer_hook is None:
        b.cache_put(key, blocks)
    return done(blocks, "llm")


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
