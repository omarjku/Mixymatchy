"""v2 steps 4-5 (docs/DECISIONS.md 23): a 1-2 sentence answer written with the Citations API, checked twice.

WRITE   Claude Haiku with the Citations API.  The evidence pool (engine/evidence.py) is ONE custom-content document,
        one content block per chunk, so every citation is a `content_block_location` whose block indices are chunk
        indices.  The Citations API cannot be combined with structured outputs (`output_config.format` -> 400), so
        the writer returns plain text blocks + citations and code parses them; the claim judge, which needs no
        citations, uses structured outputs.  Thinking off, effort low, small max_tokens, deadline, budget guard.
VERIFY  (a) deterministic binding check, per sentence against the chunks that sentence cites:
            - every sentence cites at least one chunk; at most 2 sentences; no markup, links or invisible characters
            - the sentence is cut into groups (clauses; comma parts around each value); EVERY group must be found
              inside ONE cited chunk: all its words (except a fixed list of glue words), every number with its
              unit right after it (value-unit adjacency), every date (day/month/year as written), every schedule
              (1-0-0); a dose or schedule without a drug name in its group takes the nearest drug name before it
            - negations (no, not, none, without, nicht, kein ...) must precede the same word in that chunk; "with X"
              is refused where the chunk says "without X"
            Number words, sides (left/right), polarity (positive/negative), advice, hedges and time words are NOT
            glue words, so they must be in the cited chunk itself.
        (b) claim judge: a second, independent Haiku call (structured output) splits the answer into atomic claims
            and says for each whether its cited chunks fully entail it.  Timeout or error counts as a failure.
        Any failure -> one regeneration that names the failing claim -> checked again -> else the deterministic
        compact answer (answers.py templates of the top 1-3 needs, every block citing its own chunks).
Nothing unsupported is displayed: the template is built from the facts' own fields.
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
MAX_CHARS = 420
COMPACT_CHARS = 300
COMPACT_NEEDS = 3

# glue words a sentence may add around the chunks' own words (folded, lower case); nothing that carries meaning
GLUE = set("""
a an the of in on at to for from by as and or also both her she it its this that these those which who whose
is was were are be been being has had have take takes taking dose doses
documented recorded listed noted mentioned stated reported shown shows showed found measured dated date dates
value values result results latest last most recent later yes about per each during between into there here
letter letters record patient with
""".split())
_ARTICLES = {"the", "a", "an", "her", "its", "any", "is", "was", "be", "been"}
NEGATIONS = {"no", "not", "none", "never", "without", "nicht", "kein", "keine", "keinen", "ohne", "neither", "nor"}
_MONTHS = {m.lower(): i + 1 for i, m in enumerate(A.MONTHS)}
_MONTHS.update({m.lower()[:3]: i + 1 for i, m in enumerate(A.MONTHS)})
_MONTHS.update({"sept": 9, "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "juni": 6, "juli": 7, "oktober": 10,
                "dezember": 12, "mai": 5})
_MON = r"(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|" \
       r"jun|jul|aug|sept|sep|oct|nov|dec|januar|februar|märz|maerz|juni|juli|oktober|dezember|mai)\.?"
_DATE_RX = [
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), lambda m: (int(m[1]), int(m[2]), int(m[3]))),
    (re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b"), lambda m: (int(m[3]), int(m[2]), int(m[1]))),
    (re.compile(r"\b(\d{1,2})\.?\s+" + _MON + r",?\s+(\d{4})\b", re.I),
     lambda m: (int(m[3]), _MONTHS[m[2].lower()], int(m[1]))),
    (re.compile(r"\b" + _MON + r"\s+(\d{1,2}),?\s+(\d{4})\b", re.I),
     lambda m: (int(m[3]), _MONTHS[m[1].lower()], int(m[2]))),
    (re.compile(r"\b" + _MON + r",?\s+(\d{4})\b", re.I), lambda m: (int(m[2]), _MONTHS[m[1].lower()], None)),
    (re.compile(r"\b(\d{1,2})/(\d{4})\b"), lambda m: (int(m[2]), int(m[1]), None)),
    (re.compile(r"(?<![\d.,/-])((?:19|20)\d{2})(?![\d.,/%]|\s*(?:mg|kg|g|ml)\b)"), lambda m: (int(m[1]), None, None)),
]
_SCHED_RX = re.compile(r"(?<![\d.,])(\d|½)\s*[-–—]\s*(\d|½)\s*[-–—]\s*(\d|½)(?:\s*[-–—]\s*(\d|½))?(?!\d|[.,]\d)")
_UNITS = r"(%|percent|per cent|mmol/mol|mmol/l|mg/dl|mmhg|µg|μg|ug|mcg|mg|kg|g|ml|cm|mm|bpm|/min|months?|years?|" \
         r"weeks?|days?|hours?|h|allred)"
_NUM_RX = re.compile(r"(?<![\w.,])[-+−]?(\d+(?:[.,]\d+)?)(?:\s*" + _UNITS + r"(?![a-zµμ]))?", re.I)
_WORD_RX = re.compile(r"[^\W\d_][\w'’-]*", re.U)
_BAD_RX = re.compile(r"[<>`*#\[\]{}]|https?:|www\.", re.I)
_UNIT_CANON = {"percent": "%", "per cent": "%", "μg": "µg", "ug": "µg", "mcg": "µg", "month": "months",
               "year": "years", "week": "weeks", "day": "days", "hour": "h", "hours": "h"}


# ----------------------------------------------------------------- text analysis

def fold(text):
    from .understand import fold as f
    return f(str(text or "")).lower()


def _canon_num(s):
    s = s.replace(",", ".")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s.lstrip("0") or "0"


def _unit(u):
    u = (u or "").lower()
    return _UNIT_CANON.get(u, u) if u else None


def _norm_word(w):
    w = w.strip("'’-").replace("’", "'")
    if w.endswith("'s"):
        w = w[:-2]
    if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
        w = w[:-1]
    return w


def analyse(text):
    """-> dict(dates=[(y,m,d)], scheds=[...], nums=[(num, unit|None)], words=[...], tokens=[...]) of a text."""
    t = fold(text)
    dates = []
    for rx, conv in _DATE_RX:
        def sub(m, conv=conv):
            try:
                dates.append(conv(m))
            except Exception:
                return m.group(0)
            return " qqd%s " % _code(len(dates) - 1)  # a placeholder keeps the date's position
        t = rx.sub(sub, t)
    scheds = []

    def ssub(m):
        scheds.append("-".join(x for x in m.groups() if x is not None))
        return " "
    t = _SCHED_RX.sub(ssub, t)
    nums = []

    def nsub(m):
        nums.append((_canon_num(m.group(1)), _unit(m.group(2))))
        return " "
    t2 = _NUM_RX.sub(nsub, t)
    toks = [_norm_word(w) for w in _WORD_RX.findall(t2)]
    toks = [w for w in toks if w]
    seq = [dates[_decode(w[3:])] if w.startswith("qqd") else w for w in toks]
    words = [w for w in toks if not w.startswith("qqd")]
    return {"dates": dates, "scheds": scheds, "nums": nums, "words": words, "seq": seq}


def _code(i):
    return "".join(chr(97 + int(d)) for d in str(i))


def _decode(s):
    return int("".join(str(ord(ch) - 97) for ch in s))


class Chunk:
    """A chunk's text, prepared once for the binding check."""

    def __init__(self, c):
        self.id = c["id"]
        self.raw = c["text"]
        a = analyse(c["text"])
        self.dates, self.scheds = a["dates"], set(a["scheds"])
        self.nums = set(a["nums"])
        self.bare = {n for n, _u in a["nums"]}
        self.seq = a["words"]
        self.dseq = a["seq"]  # words and dates in order
        head, _sep, body = c["text"].partition(": ")
        self.words = self._set(analyse(body)["words"] if _sep else self.seq)
        self.label_words = self._set(analyse(head)["words"]) if _sep else set()  # the need label (KB wording)
        self.nums_count = {}
        for n in a["nums"]:
            self.nums_count[n] = self.nums_count.get(n, 0) + 1

    @staticmethod
    def _set(words):
        out = set(words)
        for w in list(out):
            out |= {p for p in re.split(r"[-']", w) if len(p) >= 2}
        return out

    def has_word(self, w, heading=False):
        ws = self.words | self.label_words if heading else self.words
        return w in ws or all(p in ws for p in re.split(r"[-']", w) if len(p) >= 2)

    def has_date(self, d):
        y, m, dd = d
        return any(y == Y and (m is None or m == M) and (dd is None or dd == D) for Y, M, D in self.dates)

    def follows(self, first, then, window=3):
        """`then` occurs within `window` words after `first` in this chunk."""
        idx = [i for i, w in enumerate(self.seq) if w == first]
        return any(then in self.seq[i + 1:i + 1 + window] for i in idx)


def _split_outside(text, rx, with_sep=False):
    """Split `text` at matches of `rx` that are not inside parentheses (with_sep: [(piece, separator after)])."""
    out, seps, depth, last = [], [], 0, 0
    marks = {m.start(): m.end() for m in rx.finditer(text)}
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if depth == 0 and i in marks:
            out.append(text[last:i])
            seps.append(text[i:marks[i]].strip())
            last = i = marks[i]
            continue
        i += 1
    out.append(text[last:])
    seps.append("")
    if with_sep:
        return [(x.strip(" ,;:"), sp) for x, sp in zip(out, seps) if x.strip(" ,;:")]
    return [x for x in (s.strip(" ,;:") for s in out) if x]


_SENT_RX = re.compile(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ\"(])")
_CLAUSE_RX = re.compile(r";|:(?!\d)")
_PART_RX = re.compile(r",(?!\d)|\s+(?:and|plus|und|&)\s+", re.I)


def sentences(text):
    out = []
    for s in _SENT_RX.split(text.strip()):
        if out and re.search(r"(?:\b[a-z]\.){1,3}$|\b(?:dr|e\.g|i\.e|vs|approx|ca)\.$", out[-1], re.I):
            out[-1] += " " + s  # 's.c. 1-0-1', 'Dr. ...': not a sentence end
        elif s.strip():
            out.append(s.strip())
    return out


def _pieces(parts):
    """Parts -> pieces: a part that is only a side / polarity / date joins the piece before it."""
    out = []
    for p in parts:
        a = analyse(p)
        content = [w for w in a["words"] if w not in GLUE]
        if out and not a["nums"] and not a["scheds"] and (not content or set(content) <= SIDE_POLARITY):
            out[-1] += ", " + p
        else:
            out.append(p)
    return out


def groups(sentence):
    """A sentence -> [(group text, pieces)]: each group must sit inside ONE cited chunk (see the module doc).
    pieces: when the whole group is in no single chunk, each piece in one chunk is accepted instead (a list of
    separate statements: 'HER2 negative, oestrogen receptor positive (100% ...)'); a side, polarity or date part
    never stands alone."""
    out = []
    for clause, sep in _split_outside(sentence, _CLAUSE_RX, with_sep=True):
        head = sep == ":"  # a heading ('Before contrast:') may use the need label's words
        parts = _split_outside(clause, _PART_RX)
        info = [analyse(p) for p in parts]
        core = [bool(a["nums"] or a["scheds"]) for a in info]
        if not any(core):  # no values: each piece is a group
            out += [(p, [p], head) for p in _pieces(parts)]
            continue
        bucket = {i: [p] for i, (p, c) in enumerate(zip(parts, core)) if c}
        cores = sorted(bucket)
        for i, (p, c) in enumerate(zip(parts, core)):
            if c:
                continue
            nxt = next((j for j in cores if j > i), None)
            prv = next((j for j in reversed(cores) if j < i), None)
            dated = bool(info[i]["dates"])
            target = prv if (dated and prv is not None) or nxt is None else nxt
            if target > i:
                bucket[target].insert(0, p)
            else:
                bucket[target].append(p)
        out += [(", ".join(bucket[j]), _pieces(bucket[j]), head) for j in cores]
    return out


SIDE_POLARITY = {"left", "right", "bilateral", "links", "rechts", "positive", "negative", "positiv", "negativ"}


# ----------------------------------------------------------------- (a) deterministic binding check

def n_unit_repeat(cnt, c):
    """A value with its unit written more often than the chunk writes it ('100 mg 100 mg')."""
    return any(n[1] and k_ > c.nums_count.get(n, 0) for n, k_ in cnt.items())


def _dates_bound(seq, c):
    """A date right after a content word ('admitted 14/06/2015', 'Weight 78 kg (14 June 2015)') keeps that word:
    in the chunk the same word stands at most 3 words before a matching date (swapped dates inside one chunk)."""
    for i, d in enumerate(seq):
        if not isinstance(d, tuple) or i == 0:
            continue
        prev = seq[i - 1]
        if isinstance(prev, tuple) or prev in GLUE or prev in _ARTICLES:
            continue
        ok = False
        for j, x in enumerate(c.dseq):
            if isinstance(x, tuple) and _date_fits(d, x) and prev in c.dseq[max(0, j - 3):j]:
                ok = True
                break
        if not ok:
            return False
    return True


def _date_fits(d, x):
    return d[0] == x[0] and (d[1] is None or d[1] == x[1]) and (d[2] is None or d[2] == x[2])


def _side_ok(c, seq, i):
    """A side / polarity word keeps its neighbour: the nearest content word before it in the sentence group must
    stand within 4 words before it in the chunk (none before: the next content word, within 4 words either side)."""
    w = seq[i]
    prev = next((x for x in reversed(seq[:i]) if x not in GLUE and x not in SIDE_POLARITY), None)
    nxt = next((x for x in seq[i + 1:] if x not in GLUE and x not in SIDE_POLARITY), None)
    for j, x in enumerate(c.seq):
        if x != w:
            continue
        if prev is not None:
            if prev in c.seq[max(0, j - 4):j]:
                return True
        elif nxt is None or nxt in c.seq[max(0, j - 4):j] + c.seq[j + 1:j + 5]:
            return True
    return False


def _drug_words(st):
    key = id(st)
    if key not in _DRUGS:
        ws = set()
        for f in st.facts:
            a = f.get("attrs") or {}
            for x in (a.get("generic"), a.get("brand")):
                if x:
                    ws |= {_norm_word(w) for w in _WORD_RX.findall(fold(x)) if len(w) >= 4}
        _DRUGS[key] = ws - GLUE
    return _DRUGS[key]


_DRUGS = {}


def _group_ok(g, before, chunks, drugs, heading=False):
    """-> (ok, chunk id | None, why).  `before`: the sentence text before this group (for the drug name)."""
    a = analyse(g)
    words = [w for w in a["words"] if w not in GLUE]
    need_drug = None
    doses = [n for n in a["nums"] if n[1] in ("mg", "µg", "g", "ml")] or a["scheds"]
    if doses and not (set(words) & drugs):
        prev = [w for w in analyse(before)["words"] if w in drugs]
        need_drug = prev[-1] if prev else None
    seq = [w for w in a["words"]]
    why = "no cited chunk holds '%s'" % g.strip()[:80]
    for c in chunks:
        if not all(c.has_word(w, heading) for w in words):
            continue
        if need_drug and not c.has_word(need_drug):
            continue
        if not all(n in c.nums if n[1] else n[0] in c.bare for n in a["nums"]):
            continue
        cnt = {}
        for n in a["nums"]:
            cnt[n] = cnt.get(n, 0) + 1
        if n_unit_repeat(cnt, c):
            continue
        if not all(c.has_date(d) for d in a["dates"]):
            continue
        if not all(s in c.scheds for s in a["scheds"]):
            continue
        bad = False
        for i, w in enumerate(seq):
            if w in NEGATIONS:  # the negated word must follow the negation in the chunk as well
                nxt = next((x for x in seq[i + 1:] if x not in _ARTICLES and x not in NEGATIONS), None)
                if nxt and not c.follows(w, nxt):
                    bad = True
            if w == "with" and i + 1 < len(seq):
                nxt = seq[i + 1]
                if (c.follows("without", nxt, 1) or c.follows("ohne", nxt, 1)) and not c.follows("with", nxt, 1):
                    bad = True
        for i, w in enumerate(seq):
            if w in SIDE_POLARITY and not _side_ok(c, seq, i):
                bad = True
        if not _dates_bound(a["seq"], c):
            bad = True
        if bad:
            continue
        return True, c.id, None
    return False, None, why


def check(st, blocks, chunks_by_id):
    """(a) the binding check.  blocks: [{"text", "chunks": [ids]}] -> (ok, reasons, per-sentence chunk use)."""
    text = "".join(b["text"] for b in blocks)
    reasons = []
    if not text.strip():
        return False, ["empty answer"], []
    if any(unicodedata.category(ch) in ("Cf", "Co", "Cs") for ch in text):
        return False, ["invisible or private characters"], []
    if _BAD_RX.search(text):
        return False, ["markup or link"], []
    if len(text) > MAX_CHARS:
        return False, ["too long (%d characters)" % len(text)], []
    sents = sentences(text)
    if len(sents) > MAX_SENTENCES:
        return False, ["%d sentences (at most %d)" % (len(sents), MAX_SENTENCES)], []
    # which chunks each sentence cites (a sentence spans the blocks that overlap it)
    spans, pos = [], 0
    for b in blocks:
        spans.append((pos, pos + len(b["text"]), [c for c in b.get("chunks") or [] if c in chunks_by_id]))
        pos += len(b["text"])
    drugs = _drug_words(st)
    used = []
    cursor = 0
    for s in sents:
        start = text.find(s, cursor)
        end = start + len(s)
        cursor = end
        cited = list(dict.fromkeys(c for a, b_, cs in spans if a < end and b_ > start for c in cs))
        if not cited:
            reasons.append("uncited sentence: '%s'" % s[:80])
            continue
        prepared = [chunks_by_id[c] for c in cited]
        pos_g = 0
        hits = []
        for g, pieces, head in groups(s):
            at = s.find(g.split(",")[0].strip()[:20], pos_g)
            before = s[:at if at >= 0 else pos_g]
            ok, cid, why = _group_ok(g, before, prepared, drugs, head)
            if ok:
                hits.append(cid)
            elif len(pieces) > 1:  # separate statements side by side: each in a chunk of its own
                res = []
                for pc in pieces:
                    at2 = s.find(pc[:20], pos_g)
                    res.append(_group_ok(pc, s[:at2 if at2 >= 0 else pos_g], prepared, drugs, head))
                ok = all(r[0] for r in res)
                hits += [r[1] for r in res if r[0]]
            if not ok:
                reasons.append(why)
            pos_g = max(pos_g, at if at >= 0 else pos_g)
        used.append({"sentence": s, "cited": cited, "groups_in": hits})
    return not reasons, reasons, used


def prepare(chunks):
    return {c["id"]: Chunk(c) for c in chunks}


# ----------------------------------------------------------------- the writer (Citations API)

STYLE = (
    "You are the answer writer of Second Eye. A clinician asked a question about ONE patient. Answer it from the "
    "evidence document only: its blocks are facts taken word for word from the patient's letters, 'Not documented: "
    "X' blocks and 'Letters disagree' blocks.\n"
    "Rules:\n"
    "- ONE sentence, two at most, in English. Only what the question needs: the 1-3 most relevant facts.\n"
    "- Cite the block for every claim. Copy names, values, units, doses, schedules (1-0-0), dates and sides "
    "exactly as the cited block writes them, in the same block; never combine a value of one block with a "
    "name or date of another.\n"
    "- Use the blocks' own words. The only words you may add are: the, of, in, on, at, to, for, from, by, as, "
    "and, or, also, both, her, she, is, was, were, has, had, takes, documented, recorded, listed, latest, last, "
    "dated, with, yes.\n"
    "- If the question asks for something the evidence does not contain, say it is 'not documented', citing the "
    "'Not documented' block when there is one.\n"
    "- Never add anything that is not in the blocks: no advice, no interpretation, no normal ranges, no "
    "numbers written as words, no 'possibly', 'since', 'until', 'currently', no drug classes, no causes.\n"
    "- If letters disagree about a fact you state, say so briefly from the 'Letters disagree' block."
)


def writer_params(question, chunks, feedback=None):
    q = "Question: " + " ".join(str(question or "").split())[:600]
    if feedback:
        q += ("\nA first answer was rejected by the fact check: %s. Write a new answer that states only what the "
              "cited blocks say, in their own words." % feedback)
    return dict(
        model=llm.model(),
        max_tokens=400,
        thinking={"type": "disabled"},
        system=[{"type": "text", "text": STYLE, "cache_control": {"type": "ephemeral"}}],
        output_config={"effort": "low"},  # no output_config.format: structured outputs + citations -> 400
        messages=[{"role": "user", "content": [
            {"type": "document", "title": "Evidence from the patient's letters",
             "source": {"type": "content", "content": [{"type": "text", "text": c["text"]} for c in chunks]},
             "citations": {"enabled": True}},
            {"type": "text", "text": q},
        ]}],
    )


def _get(x, name, default=None):
    return x.get(name, default) if isinstance(x, dict) else getattr(x, name, default)


def parse_cited(msg, chunks):
    """API message -> [{"text", "chunks": [chunk ids]}] (content_block_location citations; block index = chunk)."""
    out = []
    for b in _get(msg, "content") or []:
        if _get(b, "type") != "text":
            continue
        ids = []
        for c in _get(b, "citations") or []:
            if _get(c, "type") != "content_block_location" or _get(c, "document_index", 0) != 0:
                continue
            s, e = _get(c, "start_block_index"), _get(c, "end_block_index")
            if not isinstance(s, int):
                continue
            e = e if isinstance(e, int) and e > s else s + 1
            ids += [chunks[i]["id"] for i in range(s, min(e, len(chunks)))]
        out.append({"text": _get(b, "text") or "", "chunks": list(dict.fromkeys(ids))})
    return out


# ----------------------------------------------------------------- (b) the claim judge (structured output)

JUDGE = (
    "You are the fact checker of Second Eye, independent of the writer. You get an answer, sentence by sentence, "
    "with the evidence blocks each sentence cites (taken word for word from a patient's letters). Split the answer "
    "into atomic claims (one fact each: a name, value, unit, dose, schedule, date, side, status, cause, time "
    "relation, 'not documented'). For each claim set entailed=true ONLY if the cited blocks state it fully and "
    "exactly: same numbers and units, same dates, same side, same polarity (positive/negative, with/without, "
    "present/absent), same time relation (current vs earlier, before/after), same cause and direction. Anything "
    "the blocks do not say - advice, interpretation, normal ranges, a hedge, a drug class, a combination of two "
    "blocks into a new fact - is entailed=false. Answer only with the JSON."
)
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"claims": {"type": "array", "items": {
        "type": "object",
        "properties": {"claim": {"type": "string"}, "evidence_ids": {"type": "array", "items": {"type": "string"}},
                       "entailed": {"type": "boolean"}},
        "required": ["claim", "evidence_ids", "entailed"], "additionalProperties": False}}},
    "required": ["claims"], "additionalProperties": False,
}


def judge_params(used, chunks_by_text):
    payload = [{"sentence": u["sentence"],
                "cited_evidence": [{"id": c, "text": chunks_by_text[c]} for c in u["cited"]]} for u in used]
    return dict(
        model=llm.model(),
        max_tokens=700,
        thinking={"type": "disabled"},
        system=[{"type": "text", "text": JUDGE, "cache_control": {"type": "ephemeral"}}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
        messages=[{"role": "user", "content": json.dumps({"answer": payload}, ensure_ascii=False)}],
    )


def parse_judge(msg):
    """-> (ok, verdicts [{"claim", "evidence_ids", "entailed"}], failing claim | None)."""
    txt = next((_get(x, "text", "") for x in _get(msg, "content") or [] if _get(x, "type") == "text"), "")
    data = json.loads(txt)
    claims = [c for c in data.get("claims") or [] if isinstance(c, dict)]
    if not claims:
        return False, [], "the fact check found no claim"
    bad = next((c for c in claims if c.get("entailed") is not True), None)
    return bad is None, claims, (bad or {}).get("claim")


# ----------------------------------------------------------------- calls (deadline, budget)

def _timeout(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return float(default)


def _call(params, timeout, info, tag):
    """One model call with a hard deadline -> message or None (info records why)."""
    b = llm_budget.budget()
    if not b.reserve():
        info.setdefault("skipped", {})[tag] = b.why_blocked() or "budget"
        return None
    fut = llm._pool.submit(llm._call, params)
    t = time.perf_counter()
    try:
        msg = fut.result(timeout=max(0.05, timeout))
    except FutureTimeout:
        b.error()
        info.setdefault("skipped", {})[tag] = "timeout"
        return None
    except Exception as e:
        b.error()
        info.setdefault("skipped", {})[tag] = "error: %s" % type(e).__name__
        return None
    finally:
        info.setdefault("ms", {})[tag] = round((time.perf_counter() - t) * 1000, 1)
    try:
        if _get(msg, "usage") is not None:
            info["cost_eur"] = info.get("cost_eur", 0.0) + b.record(params["model"], msg.usage)
    except Exception:
        pass
    if _get(msg, "stop_reason") in ("refusal", "max_tokens"):
        info.setdefault("skipped", {})[tag] = "stop_reason: %s" % _get(msg, "stop_reason")
        return None
    return msg


# ----------------------------------------------------------------- the compact deterministic answer

def compact(st, k, ranked, chunks_by_id):
    """Templates (engine/answers.py) of the top needs, each block citing its own chunks; 1-2 sentences."""
    blocks, total = [], 0
    for n, ids in ranked[:COMPACT_NEEDS]:
        t = A.template(st, k, n).strip().rstrip(".")
        if blocks and total + len(t) > COMPACT_CHARS:
            break
        sep = "" if not blocks else (". " if len(blocks) == 1 else "; ")
        if len(blocks) == 1:
            t = t[:1].upper() + t[1:]
        else:
            t = t if not blocks else A._low(t)
        blocks.append({"text": sep + t, "chunks": [i for i in ids if i in chunks_by_id]})
        total += len(sep) + len(t)
    if blocks:
        blocks[-1]["text"] += "."
    return blocks


# ----------------------------------------------------------------- the whole step

def _cache_key(question, chunks):
    return ("answer_v2", llm.model(), " ".join(str(question or "").lower().split()),
            tuple(c["text"] for c in chunks))


_writer_hook = None  # eval without a key: fn(question, chunks, feedback, compact blocks) -> blocks, not the API
_judge_hook = None   # eval without a key: fn(used sentences, chunks) -> (ok, verdicts, failing claim)


def set_writer(fn):
    global _writer_hook
    _writer_hook = fn


def set_judge(fn):
    global _judge_hook
    _judge_hook = fn


def _write(question, chunks, feedback, info, timeout, fallback=()):
    if _writer_hook is not None:
        info["called"] = True
        return _writer_hook(question, chunks, feedback, [dict(b) for b in fallback])
    msg = _call(writer_params(question, chunks, feedback), timeout, info, "writer" if not feedback else "rewriter")
    info["called"] = True
    return parse_cited(msg, chunks) if msg is not None else None


def _judge(used, chunks, info, timeout):
    if _judge_hook is not None:
        return _judge_hook(used, chunks)
    texts = {c["id"]: c["text"] for c in chunks}
    msg = _call(judge_params(used, texts), timeout, info, "judge")
    if msg is None:
        return False, [], "fact check unavailable (%s)" % (info.get("skipped") or {}).get("judge")
    try:
        return parse_judge(msg)
    except Exception as e:
        return False, [], "fact check unreadable (%s)" % type(e).__name__


def writer_available(use_llm):
    return _writer_hook is not None or (use_llm and llm.available()
                                        and os.environ.get("SECOND_LOOK_ANSWERS_LLM", "1") != "0")


def answer(st, k, question, chunks, ranked, use_llm=True, t0=None):
    """-> (answer dict, stats).  answer: {"blocks", "text", "origin" llm|regenerated|template, "verified"}."""
    t0 = t0 if t0 is not None else time.perf_counter()
    prepared = prepare(chunks)
    stats = {"origin": "template", "called": False, "judge": [], "rejected": [], "skipped": {}, "ms": {},
             "cost_eur": 0.0}
    fallback = compact(st, k, ranked, prepared)

    def done(blocks, origin):
        stats["origin"] = origin
        stats["ms"]["total"] = round((time.perf_counter() - t0) * 1000, 1)
        stats["cost_eur"] = round(stats.get("cost_eur") or 0.0, 6)
        return {"blocks": blocks, "text": "".join(b["text"] for b in blocks).strip(), "origin": origin,
                "verified": True}, stats

    if not ranked or not chunks:
        stats["skipped"]["writer"] = "no evidence"
        return done(fallback, "template")
    if not writer_available(use_llm):
        stats["skipped"]["writer"] = "disabled" if not llm.enabled() or not use_llm else "no key"
        return done(fallback, "template")
    b = llm_budget.budget()
    key = _cache_key(question, chunks)
    hit = b.cache_get(key) if _writer_hook is None else None
    if hit is not None:
        stats["cached"] = True
        return done(hit["blocks"], hit["origin"])
    deadline = _timeout("SECOND_LOOK_V2_DEADLINE", "8.0")
    w_to = _timeout("SECOND_LOOK_V2_WRITER_TIMEOUT", "3.0")
    j_to = _timeout("SECOND_LOOK_V2_JUDGE_TIMEOUT", "2.0")
    feedback = None
    for attempt in (1, 2):
        left = deadline - (time.perf_counter() - t0)
        if attempt == 2 and left < w_to + j_to * 0.5:
            stats["skipped"]["rewriter"] = "no time left"
            break
        blocks = _write(question, chunks, feedback, stats, min(w_to, max(0.2, left)), fallback)
        if not blocks:
            break
        blocks = [{"text": x["text"], "chunks": x.get("chunks") or []} for x in blocks]
        ok, reasons, used = check(st, blocks, prepared)
        verdicts = []
        if ok:
            left = deadline - (time.perf_counter() - t0)
            ok, verdicts, bad = _judge(used, chunks, stats, min(j_to, max(0.2, left)))
            stats["judge"].append({"attempt": attempt, "ok": ok, "claims": verdicts})
            if not ok:
                reasons = ["fact check: '%s' not supported by its cited evidence" % (bad or "?")]
                stats["rejected"].append({"attempt": attempt, "layer": "judge", "reasons": reasons})
        else:
            stats["rejected"].append({"attempt": attempt, "layer": "binding", "reasons": reasons[:4]})
        if ok:
            origin = "llm" if attempt == 1 else "regenerated"
            if _writer_hook is None:
                b.cache_put(key, {"blocks": blocks, "origin": origin})
            return done(blocks, origin)
        feedback = "; ".join(reasons[:2])
    return done(fallback, "template")


def sources(blocks, chunks_by_id):
    """The Source chips: one per cited chunk, in order of first citation."""
    out, seen = [], set()
    for bl in blocks:
        for cid in bl.get("chunks") or []:
            c = chunks_by_id.get(cid)
            if c and cid not in seen and c.get("passages"):
                seen.add(cid)
                out.append({"chunk": cid, "kind": c["kind"], "label": c["text"].split(":")[0][:60],
                            "passages": list(c["passages"]), "facts": list(c.get("facts") or [])})
    return out
