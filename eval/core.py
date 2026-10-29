"""Core checks of the eval harness (stdlib only).

Three families of checks over data/build/{docs,passages,facts}.json:

* invariants   -- the data contract of docs/contracts.md
* coverage     -- can the 15 case questions be answered from linked facts
* contradiction readiness -- do the facts needed by contradiction rules exist
"""
import html
import json
import os
import re
import unicodedata
from collections import defaultdict

# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class Build:
    """The three build artefacts plus indexes."""

    def __init__(self, docs, passages, facts):
        self.docs = docs or {}
        self.passages = passages or []
        self.facts = facts or []
        self.passage_by_id = {}
        for p in self.passages:
            self.passage_by_id.setdefault(p.get("id"), p)
        self.fact_by_id = {f.get("id"): f for f in self.facts}

    @classmethod
    def from_dir(cls, build_dir):
        return cls(
            load_json(os.path.join(build_dir, "docs.json"), {}),
            load_json(os.path.join(build_dir, "passages.json"), []),
            load_json(os.path.join(build_dir, "facts.json"), []),
        )

    def fact_docs(self, fact):
        """Doc ids of the (existing) passages a fact links to."""
        out = set()
        for pid in fact.get("passage_ids") or []:
            p = self.passage_by_id.get(pid)
            if p is not None:
                out.add(p.get("doc_id"))
        return out

    def fact_passages(self, fact):
        return [self.passage_by_id[pid] for pid in fact.get("passage_ids") or []
                if pid in self.passage_by_id]


def display_text_from_raw(raw):
    """Contract: <BR> replaced BEFORE unescaping."""
    return html.unescape(raw.replace("<BR>", "\n"))


# --------------------------------------------------------------------------
# text normalisation and token matching
# --------------------------------------------------------------------------

_UNIT_RE = re.compile(r"(\d)\s*(mmhg|mg|μg|mcg|ug|kg|cm|mm|ml|g|iu|ie)(?![a-zäöü])")


def norm(s):
    """Normalise text for token matching (applied to keys and facts alike)."""
    s = unicodedata.normalize("NFKC", str(s))  # micro sign -> greek mu
    s = s.lower().replace("ß", "ss")
    s = re.sub(r"(\d),(\d)", r"\1.\2", s)  # decimal comma
    s = re.sub(r"[-_:;,()\[\]{}\"'|=*–—]", " ", s)
    s = re.sub(r"\s+%", "%", s)
    s = _UNIT_RE.sub(r"\1 \2", s)
    return re.sub(r"\s+", " ", s).strip()


def ws(s):
    return re.sub(r"\s+", " ", s or "").strip()


_alt_cache = {}


def alt_regex(alt):
    """Regex for one alternative.

    Leading word boundary if the alternative starts alphanumeric (so 'ass'
    does not hit 'klasse'); trailing boundary only if it ends in a digit
    (so '1-0-1' does not hit '1-0-1/2' and '6' does not hit '60').
    Alternatives ending in letters match as prefixes ('quadrant' hits
    'quadrantenresektion').
    """
    if alt in _alt_cache:
        return _alt_cache[alt]
    a = norm(alt)
    pre = r"(?<!\w)" if a[:1].isalnum() else ""
    post = r"(?![\d/]|\.\d)" if a[-1:].isdigit() else ""
    rx = re.compile(pre + re.escape(a) + post)
    _alt_cache[alt] = rx
    return rx


def flatten_attrs(attrs, prefix=""):
    out = []
    if isinstance(attrs, dict):
        for k, v in attrs.items():
            out.extend(flatten_attrs(v, k))
    elif isinstance(attrs, (list, tuple)):
        for v in attrs:
            out.extend(flatten_attrs(v, prefix))
    elif attrs is not None and attrs is not False:
        out.append((prefix, attrs))
    return out


def attrs_text(attrs):
    return " ".join("%s %s" % (k, v) for k, v in flatten_attrs(attrs))


def fact_search_text(fact):
    return norm(" | ".join([fact.get("label_en") or "", fact.get("quote") or "",
                            attrs_text(fact.get("attrs") or {})]))


def alt_matches(alt, fact, text):
    if alt.startswith("@date:"):
        return str(fact.get("date") or "").startswith(alt[6:])
    return alt_regex(alt).search(text) is not None


def group_matches(group, fact, text=None):
    if text is None:
        text = fact_search_text(fact)
    return any(alt_matches(a, fact, text) for a in group)


def text_group_matches(group, text):
    """Group match against plain text (passages); @date alternatives ignored."""
    t = norm(text)
    return any(alt_regex(a).search(t) for a in group if not a.startswith("@date:"))


def group_label(group):
    return "[" + " | ".join(group) + "]"


# --------------------------------------------------------------------------
# dates
# --------------------------------------------------------------------------

_MONTHS = {
    "januar": 1, "jänner": 1, "jaenner": 1, "january": 1, "februar": 2, "february": 2,
    "märz": 3, "maerz": 3, "march": 3, "april": 4, "mai": 5, "may": 5, "juni": 6,
    "june": 6, "juli": 7, "july": 7, "august": 8, "september": 9, "oktober": 10,
    "october": 10, "november": 11, "dezember": 12, "december": 12,
}
_DATE_NUM_RE = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](\d{4})")
_DATE_ISO_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_DATE_WORD_RE = re.compile(r"(?<!\d)(\d{1,2})\.?\s+([A-Za-zäöüÄÖÜ]+)\s+(\d{4})")


def dates_in_text(text):
    """ISO dates (YYYY-MM-DD) found in free text in common formats."""
    out = set()
    for d, m, y in _DATE_NUM_RE.findall(text or ""):
        if 1 <= int(m) <= 12 and 1 <= int(d) <= 31:
            out.add("%s-%02d-%02d" % (y, int(m), int(d)))
    for y, m, d in _DATE_ISO_RE.findall(text or ""):
        out.add("%s-%s-%s" % (y, m, d))
    for d, mon, y in _DATE_WORD_RE.findall(text or ""):
        m = _MONTHS.get(mon.lower())
        if m:
            out.add("%s-%02d-%02d" % (y, m, int(d)))
    return out


def date_parts(d):
    """'2016-04-xx' -> ('2016', '04', None)."""
    if not d:
        return None
    m = re.match(r"^(\d{4})(?:-(\d{2}|xx))?(?:-(\d{2}|xx))?", str(d))
    if not m:
        return None
    y, mo, dd = m.groups()
    mo = None if mo in (None, "xx") else mo
    dd = None if dd in (None, "xx") or mo is None else dd
    return (y, mo, dd)


def date_after(d, threshold):
    """True only if d is definitely after threshold (YYYY-MM-DD), at d's precision."""
    p = date_parts(d)
    if not p:
        return False
    y, mo, dd = p
    ty, tm, td = threshold[:4], threshold[5:7], threshold[8:10]
    if mo is None:
        return y > ty
    if dd is None:
        return (y, mo) > (ty, tm)
    return (y, mo, dd) > (ty, tm, td)


def day_date(d):
    p = date_parts(d)
    if p and p[1] and p[2]:
        return "%s-%s-%s" % p
    return None


# --------------------------------------------------------------------------
# numbers
# --------------------------------------------------------------------------

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
_ROMAN = {"ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8}


def _canon(tok):
    tok = tok.replace(",", ".")
    if "." in tok:
        a, b = tok.split(".", 1)
        b = b.rstrip("0")
        a = str(int(a))
        return a if not b else a + "." + b
    return str(int(tok))


def numbers_in(text):
    """Canonical numbers in text; decimals are also split into their parts so
    that '12.04.2016' supports 12, 4 and 2016 and roman numerals count."""
    out = set()
    for tok in _NUM_RE.findall(text or ""):
        out.add(_canon(tok))
        for part in re.split(r"[.,]", tok):
            if part:
                out.add(str(int(part)))
    for w in re.findall(r"(?<![A-Za-z])([IVX]{1,4})(?![A-Za-z])", text or ""):
        if w.lower() in _ROMAN:
            out.add(str(_ROMAN[w.lower()]))
    return out


_DATEY_RES = [
    re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](\d{4})(?!\d)"),     # 16.05.2016
    re.compile(r"(?<!\d)(\d{4})-(\d{2})(?:-(\d{2}))?(?!\d)"),         # 2016-05(-16)
    re.compile(r"(?<![\d.])(\d{1,2})[./](\d{4})(?!\d)"),              # 05/2016
    re.compile(r"(?<!\d)(\d{1,2})?\.?\s*(?:%s)\s+(\d{4})" % "|".join(
        sorted(_MONTHS, key=len, reverse=True)), re.I),               # (16.) May 2016
    re.compile(r"(?<![\d.,])((?:19|20)\d{2})(?![\d.,])"),              # bare year
]


def numbers_to_check(text, with_kind=False):
    """Numbers claimed by a label/attr value.  Date-like patterns are split
    into integer components (flagged as date parts); other decimals stay whole."""
    text = str(text)
    out = []
    for rx in _DATEY_RES:
        for m in rx.finditer(text):
            out += [(str(int(g)), True) for g in m.groups() if g]
        text = rx.sub(" ", text)
    for tok in _NUM_RE.findall(text):
        out.append((_canon(tok), False))
    return out if with_kind else [n for n, _k in out]


def _calc_numbers(fact):
    """Numbers declared as calculated.  Returns (set, all_exempt)."""
    nums, all_exempt = set(), False
    attrs = fact.get("attrs") or {}
    holders = [fact.get("calculated"), fact.get("derived"), fact.get("calculated_values")]
    if isinstance(attrs, dict):
        holders += [attrs.get(k) for k in ("calculated", "derived", "calc", "calculated_values")]
    for h in holders:
        if h is True:
            all_exempt = True
        elif h not in (None, False):
            for _k, v in flatten_attrs(h):
                if v is True:
                    all_exempt = True
                else:
                    nums |= set(numbers_to_check(v))
    if str(fact.get("origin") or "").lower() in ("calc", "calculated", "derived"):
        all_exempt = True
    return nums, all_exempt


# --------------------------------------------------------------------------
# invariants
# --------------------------------------------------------------------------

VALID_IPS = {"problems", "allergies", "medications", "procedures", "results", "vital_signs",
             "past_illness", "plan_of_care", "social_history", "functional_status"}
VALID_STATUS = {"current", "historical", "planned", "recommended", "unknown"}
VALID_KIND = {"line", "table_row", "sentence"}
VALID_PREC = {"day", "month", "year"}


def json_only_values(raw_dir):
    """Values that exist only in IBM JSON files, never in document text."""
    out = {"admission_dates": {}, "age": None, "cave": []}
    if not raw_dir:
        return out
    pj = load_json(os.path.join(raw_dir, "patient.json"), {}) or {}
    out["age"] = pj.get("age")
    dj = load_json(os.path.join(raw_dir, "documents.json"), {}) or {}
    for d in dj.get("documents", []):
        adm = d.get("admission") or {}
        for kind in ("admission", "discharge"):
            dt = ((adm.get(kind) or {}).get("date"))
            if dt:
                out["admission_dates"].setdefault(dt, set()).add(kind)
    cj = load_json(os.path.join(raw_dir, "cave.json"), {}) or {}
    for a in cj.get("adverseReactions", []) + cj.get("diagnoses", []):
        if not a.get("documentIds"):
            out["cave"].append(a.get("text") or "")
    return out


_ADMISSION_WORDS = re.compile(r"admission|admitted|discharg|aufnahme|aufgenommen|entlass|stay\b",
                              re.I)


def check_invariants(build, raw_dir=None):
    """Returns dict: violations (list of (code, msg)), warnings, stats."""
    V, W = [], []
    stats = defaultdict(int)
    docs = build.docs

    # (a0) display_text derived exactly as the contract says
    if raw_dir and os.path.isdir(os.path.join(raw_dir, "documents")):
        for fn in sorted(os.listdir(os.path.join(raw_dir, "documents"))):
            if not fn.endswith(".json"):
                continue
            did = fn[:-5]
            raw = load_json(os.path.join(raw_dir, "documents", fn), {})
            if did not in docs:
                V.append(("a0", "doc %s missing from docs.json" % did))
                continue
            exp = display_text_from_raw(raw.get("text", ""))
            if docs[did].get("display_text") != exp:
                V.append(("a0", "doc %s display_text differs from contract derivation" % did))
    for did, d in docs.items():
        if not d.get("date") or not re.match(r"^\d{4}-\d{2}-\d{2}$", str(d.get("date"))):
            W.append(("schema", "doc %s date %r not YYYY-MM-DD" % (did, d.get("date"))))

    # (a) passages
    seen = set()
    for p in build.passages:
        stats["passages"] += 1
        pid = p.get("id")
        if pid in seen:
            V.append(("a", "duplicate passage id %s" % pid))
        seen.add(pid)
        did = p.get("doc_id")
        if did not in docs:
            V.append(("a", "passage %s: unknown doc_id %s" % (pid, did)))
            continue
        if pid and not str(pid).startswith(str(did) + ":"):
            W.append(("schema", "passage %s id does not start with its doc_id" % pid))
        if p.get("kind") not in VALID_KIND:
            W.append(("schema", "passage %s kind %r" % (pid, p.get("kind"))))
        s, e, t = p.get("start"), p.get("end"), p.get("text")
        dt = docs[did].get("display_text") or ""
        if not isinstance(s, int) or not isinstance(e, int) or not (0 <= s <= e <= len(dt)):
            V.append(("a", "passage %s: bad offsets %r..%r" % (pid, s, e)))
            continue
        if dt[s:e] != t:
            V.append(("a", "passage %s: display_text[%d:%d]=%r != text %r"
                      % (pid, s, e, dt[s:e][:40], (t or "")[:40])))
        if not (t or "").strip():
            W.append(("schema", "passage %s is empty/whitespace" % pid))

    jo = json_only_values(raw_dir)
    fact_ids = set()
    for f in build.facts:
        stats["facts"] += 1
        fid = f.get("id")
        if fid in fact_ids:
            V.append(("e", "duplicate fact id %s" % fid))
        fact_ids.add(fid)
        quote = f.get("quote") or ""
        label = f.get("label_en") or ""

        # schema (warnings only)
        if f.get("ips_section") not in VALID_IPS:
            W.append(("schema", "fact %s ips_section %r" % (fid, f.get("ips_section"))))
        if f.get("status") not in VALID_STATUS:
            W.append(("schema", "fact %s status %r" % (fid, f.get("status"))))
        if f.get("date") and f.get("date_precision") not in VALID_PREC:
            W.append(("schema", "fact %s date_precision %r" % (fid, f.get("date_precision"))))
        if not label:
            W.append(("schema", "fact %s has no label_en" % fid))

        # (e) passage links
        pids = f.get("passage_ids") or []
        existing = [build.passage_by_id[x] for x in pids if x in build.passage_by_id]
        missing = [x for x in pids if x not in build.passage_by_id]
        if not existing:
            V.append(("e", "fact %s: no existing passage (passage_ids=%s)" % (fid, pids[:3])))
        elif missing:
            V.append(("e", "fact %s: unknown passage ids %s" % (fid, missing[:3])))

        # (b) quote
        if not quote.strip():
            V.append(("b", "fact %s: empty quote" % fid))
        else:
            for p in existing:
                if quote in (p.get("text") or ""):
                    continue
                if ws(quote) and ws(quote) in ws(p.get("text")):
                    stats["quote_ws_only"] += 1
                    continue
                V.append(("b", "fact %s: quote not in passage %s (quote=%r)"
                          % (fid, p.get("id"), quote[:50])))
            doc_ids = {p.get("doc_id") for p in existing}
            if doc_ids and not any(quote in (docs.get(d, {}).get("display_text") or "")
                                   for d in doc_ids):
                V.append(("b", "fact %s: stored quote is not an exact substring of its "
                          "document display_text" % fid))

        # (c) numbers
        qnums = numbers_in(quote)
        calc, all_exempt = _calc_numbers(f)
        date_nums = set()
        for d in [f.get("date")] + [docs.get(p.get("doc_id"), {}).get("date") for p in existing]:
            p_ = date_parts(d)
            if p_:
                date_nums |= {str(int(x)) for x in p_ if x}
        claims = [("label_en", n, k) for n, k in numbers_to_check(label, True)]
        attrs = f.get("attrs") or {}
        for k, v in flatten_attrs({k: v for k, v in attrs.items()
                                   if k not in ("calculated", "derived", "calc",
                                                "calculated_values")}
                                  if isinstance(attrs, dict) else attrs):
            if isinstance(v, bool):
                continue
            claims += [("attrs.%s" % k, n, dk) for n, dk in numbers_to_check(v, True)]
        for where, n, datey in claims:
            if n in qnums:
                continue
            if n in calc or all_exempt:
                stats["calc_exempt"] += 1
                continue
            if datey and n in date_nums:
                W.append(("c-date", "fact %s: %s number %s only supported by the fact/doc "
                          "date, not the quote" % (fid, where, n)))
                continue
            V.append(("c", "fact %s: %s number %s not in quote %r"
                      % (fid, where, n, quote[:60])))

        # (d) JSON-only values
        text_all = (label + " " + attrs_text(attrs)).lower()
        cat = str(f.get("category") or "").lower()
        if jo["age"] is not None:
            age = str(jo["age"])
            if (cat == "age" or re.search(r"\bage\b|years? old|jährig|jahre", text_all)) \
                    and re.search(r"(?<!\d)%s(?!\d)" % age, text_all) and age not in qnums:
                V.append(("d", "fact %s: age %s comes from patient.json, not a document"
                          % (fid, age)))
        for c in jo["cave"]:
            if c and (c.lower() in text_all or c.lower() in quote.lower()) \
                    and c.lower() not in " ".join((build.docs.get(p.get("doc_id"), {})
                                                   .get("display_text") or "").lower()
                                                  for p in existing):
                V.append(("d", "fact %s: cave.json entry %r has no document source"
                          % (fid, c)))
        if re.search(r"\bdrug allergy\b", label, re.I) and not re.search(
                r"contrast|km|kontrast", label + " " + quote, re.I):
            V.append(("d", "fact %s: generic 'drug allergy' looks like cave.json "
                      "(documents say contrast media allergy)" % fid))
        dday = day_date(f.get("date")) if f.get("date_precision", "day") == "day" else None
        if dday and existing:
            doc_texts = " ".join(docs.get(p.get("doc_id"), {}).get("display_text") or ""
                                 for p in existing)
            doc_dates = {docs.get(p.get("doc_id"), {}).get("date") for p in existing}
            if dday not in dates_in_text(doc_texts) and dday not in doc_dates:
                if dday in jo["admission_dates"]:
                    V.append(("d", "fact %s: date %s matches documents.json %s date but "
                              "appears nowhere in its document"
                              % (fid, dday, "/".join(sorted(jo["admission_dates"][dday])))))
                else:
                    W.append(("date", "fact %s: date %s not found in its document text"
                              % (fid, dday)))
            elif re.search(r"admission|discharge|encounter|stay", cat) and \
                    dday not in dates_in_text(quote) \
                    and dday in jo["admission_dates"] and dday not in doc_dates:
                W.append(("date", "fact %s: admission/discharge date %s not in quote "
                          "(check it is not from documents.json)" % (fid, dday)))
    stats["violations"] = len(V)
    return {"violations": V, "warnings": W, "stats": dict(stats)}


# --------------------------------------------------------------------------
# coverage
# --------------------------------------------------------------------------


def _facts_in(build, sources):
    if not sources:
        return list(build.facts)
    s = set(sources)
    return [f for f in build.facts if build.fact_docs(f) & s]


def eval_item(build, item, default_sources, texts):
    sources = item.get("sources", default_sources)
    groups = item["groups"]
    cands = _facts_in(build, sources)
    scope = item.get("scope", "fact")
    res = {"name": item.get("name", ""), "sources": sources, "pass": False,
           "facts": [], "missing": []}
    if scope == "union":
        rel = [f for f in cands if group_matches(groups[0], f, texts[f.get("id")])]
        missing = [g for g in groups
                   if not any(group_matches(g, f, texts[f.get("id")]) for f in rel)]
        res["pass"] = bool(rel) and not missing
        res["facts"] = [f.get("id") for f in rel]
        res["missing"] = missing if rel else groups
    else:
        best, best_missing = None, groups
        for f in cands:
            t = texts[f.get("id")]
            miss = [g for g in groups if not group_matches(g, f, t)]
            if not miss:
                res["pass"] = True
                res["facts"].append(f.get("id"))
            elif len(miss) < len(best_missing):
                best, best_missing = f, miss
        if not res["pass"]:
            res["missing"] = best_missing
    if not res["pass"]:
        res["nearest"] = nearest_facts(build, groups, sources, texts)
        res["passage_hints"] = passage_hints(build, groups, sources)
    return res


def nearest_facts(build, groups, sources, texts, k=3):
    scored = []
    src = set(sources or [])
    for f in build.facts:
        t = texts[f.get("id")]
        hit = [g for g in groups if group_matches(g, f, t)]
        if not hit:
            continue
        in_src = (not src) or bool(build.fact_docs(f) & src)
        scored.append((len(hit) + (0.5 if in_src else 0), f, in_src,
                       [g for g in groups if g not in hit]))
    scored.sort(key=lambda x: -x[0])
    return [{"id": f.get("id"), "docs": sorted(build.fact_docs(f)), "in_sources": ins,
             "label_en": f.get("label_en"), "quote": f.get("quote"),
             "missing": miss} for _s, f, ins, miss in scored[:k]]


def passage_hints(build, groups, sources, k=3):
    """Passages in source docs whose text matches every group that has a
    German/plain alternative (date-only groups are skipped)."""
    src = set(sources or [])
    tgroups = [g for g in groups if any(not a.startswith("@date:") for a in g)]
    out = []
    for p in build.passages:
        if src and p.get("doc_id") not in src:
            continue
        hits = sum(1 for g in tgroups if text_group_matches(g, p.get("text") or ""))
        if hits == len(tgroups) or (len(tgroups) > 2 and hits >= len(tgroups) - 1):
            linked = [f.get("id") for f in build.facts if p.get("id") in (f.get("passage_ids") or [])]
            out.append({"id": p.get("id"), "hits": hits, "of": len(tgroups),
                        "text": p.get("text"), "linked_facts": linked})
    out.sort(key=lambda x: -x["hits"])
    return out[:k]


def eval_question(build, qid, key, texts):
    sources = key.get("sources", [])
    items = [eval_item(build, it, sources, texts) for it in key.get("items", [])]
    res = {"id": qid, "question": key.get("question", ""), "mode": key.get("mode", "answer"),
           "items": items, "forbidden_hits": [], "pass": all(i["pass"] for i in items)}
    fb = key.get("forbid")
    if fb:
        ign_status = set(fb.get("ignore_status", []))
        ign_groups = fb.get("ignore_if_any", [])
        for f in build.facts:
            t = texts[f.get("id")]
            if not all(group_matches(g, f, t) for g in fb["groups"]):
                continue
            if f.get("status") in ign_status:
                continue
            if any(group_matches(g, f, t) for g in ign_groups):
                continue
            if fb.get("date_after") and not date_after(f.get("date"), fb["date_after"]):
                continue
            res["forbidden_hits"].append({"id": f.get("id"), "label_en": f.get("label_en"),
                                          "date": f.get("date"), "status": f.get("status"),
                                          "docs": sorted(build.fact_docs(f)),
                                          "why": fb.get("why", "")})
        if res["forbidden_hits"]:
            res["pass"] = False
    return res


def check_coverage(build, keys):
    texts = {f.get("id"): fact_search_text(f) for f in build.facts}
    # informational: can the English label/attrs alone (what the screen shows) answer it?
    ltexts = {f.get("id"): norm((f.get("label_en") or "") + " | " + attrs_text(f.get("attrs") or {}))
              for f in build.facts}
    out = []
    for qid in sorted(k for k in keys if not k.startswith("_")):
        q = eval_question(build, qid, keys[qid], texts)
        for it, spec in zip(q["items"], keys[qid].get("items", [])):
            lr = eval_item(build, spec, keys[qid].get("sources", []), ltexts)
            it["label_pass"] = lr["pass"]
            it["label_missing"] = lr["missing"]
        q["label_pass"] = all(i["label_pass"] for i in q["items"])
        out.append(q)
    return out


# --------------------------------------------------------------------------
# contradiction readiness
# --------------------------------------------------------------------------

_LEFT = re.compile(r"\b(left|links|linke[nrs]?|li\.|sin\.|sinistra|sinister)(?!\w)", re.I)
_RIGHT = re.compile(r"\b(right|rechts|rechte[nrs]?|re\.|dext\.|dextra)(?!\w)", re.I)


def fact_side(f):
    side = str((f.get("attrs") or {}).get("side") or "").strip().lower()
    if side in ("left", "links", "l", "li", "li.", "sin", "sinister"):
        return "left"
    if side in ("right", "rechts", "r", "re", "re.", "dext"):
        return "right"
    for txt in (f.get("label_en") or "", f.get("quote") or ""):
        lft, rgt = bool(_LEFT.search(txt)), bool(_RIGHT.search(txt))
        if lft != rgt:
            return "left" if lft else "right"
    return None


def _num_value(f, words):
    """Numeric value of a measurement fact: attrs.value, else the first number
    after one of `words` in label/quote, else the first number in the label."""
    v = (f.get("attrs") or {}).get("value")
    try:
        if v is not None:
            return float(str(v).replace(",", "."))
    except ValueError:
        pass
    for txt in (f.get("label_en") or "", f.get("quote") or ""):
        m = re.search(r"(?:%s)\D{0,15}?(\d+(?:[.,]\d+)?)" % words, txt, re.I)
        if m:
            return float(m.group(1).replace(",", "."))
    m = re.search(r"\d+(?:[.,]\d+)?", f.get("label_en") or "")
    return float(m.group(0).replace(",", ".")) if m else None


def _measure_kind(f):
    cat = str(f.get("category") or "").lower()
    lab = (f.get("label_en") or "").lower().strip()
    for kind, rx in (("bmi", r"^(bmi|body.mass)"), ("height", r"^(height|body height|größe)"),
                     ("weight", r"^(weight|body weight|gewicht)\b")):
        if cat == kind or re.search(rx, cat) or re.search(rx, lab):
            return kind
    return None


def _fact_dates(build, f):
    ds = set()
    dd = day_date(f.get("date"))
    if dd:
        ds.add(dd)
    ds |= dates_in_text(f.get("quote") or "")
    return ds


BMI_DOCS = (("12340012", False), ("12340014", False), ("12340018", True))


def check_contradictions(build, bmi_docs=BMI_DOCS):
    R = {"checks": [], "notes": []}

    # 1. carotid side
    carotid = []
    for f in build.facts:
        t = norm(" ".join([f.get("label_en") or "", f.get("quote") or "",
                           str(f.get("category") or "")]))
        if re.search(r"carotis|karotis|carotid", t) and \
                re.search(r"stenos|plaque|einengung|flussgeschwindigkeit|sklerose|sclerosis", t):
            carotid.append((f, fact_side(f), bool(re.search(r"interna|internal|\bica\b|\baci\b", t))))
    left = [(f, ica) for f, s, ica in carotid if s == "left"]
    right = [(f, ica) for f, s, ica in carotid if s == "right"]
    right_ica = [f for f, ica in right if ica]
    left_ica = [f for f, ica in left if ica]
    ok = bool(right_ica and left_ica)

    def _fl(fs):
        return ", ".join("%s(%s)" % (f.get("id"), "/".join(sorted(build.fact_docs(f))))
                         for f in fs[:8]) or "none"

    R["checks"].append({
        "name": "Carotid stenosis side (left vs right internal carotid)",
        "ready": ok,
        "detail": "left ICA facts: %s; right ICA facts: %s; side-unknown carotid facts: %d"
                  % (_fl(left_ica), _fl(right_ica),
                     sum(1 for _f, s, _i in carotid if s is None)),
        "fix": None if ok else
        "Extract a carotid-stenosis fact per duplex sentence/summary (incl. the 12340012 duplex "
        "paragraph that names the right side and its 'Gesamtbeurteilung' naming the left) with "
        "attrs.side set and 'internal carotid' in label_en.",
    })

    # 2. BMI per document
    for did, control in bmi_docs:
        vals = {}
        for f in build.facts:
            if did not in build.fact_docs(f):
                continue
            k = _measure_kind(f)
            if k and (k not in vals or vals[k][1] is None):
                words = {"bmi": "bmi", "height": "größe|height", "weight": "gewicht|weight"}[k]
                vals[k] = (f.get("id"), _num_value(f, words))
        have = all(vals.get(k) and vals[k][1] for k in ("height", "weight", "bmi"))
        detail = ", ".join("%s=%s(%s)" % (k, vals[k][1], vals[k][0]) for k in
                           ("height", "weight", "bmi") if k in vals) or "none"
        verdict = ""
        if have:
            h, w, b = vals["height"][1], vals["weight"][1], vals["bmi"][1]
            if h > 3:
                h = h / 100.0
            calc = w / (h * h)
            mism = abs(calc - b) > 1.0
            verdict = "; computed BMI %.1f vs stated %s -> %s" % (
                calc, b, "CONTRADICTION" if mism else "consistent (must NOT be flagged)")
        R["checks"].append({
            "name": "BMI vs height/weight in %s%s" % (did, " (control)" if control else ""),
            "ready": have,
            "detail": detail + verdict,
            "fix": None if have else
            "Extract separate height, weight and BMI facts from the vital-sign lines of %s "
            "(category height/weight/bmi, attrs.value numeric)." % did,
        })

    # 3. admission dates in 12340018
    adm_dates = defaultdict(list)
    for f in build.facts:
        if "12340018" not in build.fact_docs(f):
            continue
        head = " ".join([str(f.get("category") or ""), f.get("label_en") or ""])
        t = head + " " + (f.get("quote") or "")
        if not re.search(r"admission|admitted|aufnahme|aufgenommen", t, re.I):
            continue
        if re.search(r"entlass|discharg", head, re.I) and \
                not re.search(r"admission|admitted|aufnahme", head, re.I):
            continue  # a discharge fact that merely quotes the header line
        for d in _fact_dates(build, f):
            adm_dates[d].append(f.get("id"))
    ok = "2016-04-10" in adm_dates and "2016-04-12" in adm_dates
    R["checks"].append({
        "name": "Admission date in 12340018 (10.04.2016 header vs 12.04.2016 course text)",
        "ready": ok,
        "detail": "admission dates found: %s" % (
            ", ".join("%s<-%s" % (d, ",".join(v)) for d, v in sorted(adm_dates.items())) or "none"),
        "fix": None if ok else
        "Extract admission facts (category 'admission') with dates from BOTH the 12340018 header "
        "line and the 'Therapie und Verlauf' sentence; set fact.date to the stated day.",
    })

    # 4. biopsy date 12340016 vs 12340018
    bio = defaultdict(lambda: defaultdict(list))
    for f in build.facts:
        t = norm(" ".join([str(f.get("category") or ""), f.get("label_en") or "",
                           f.get("quote") or ""]))
        if re.search(r"biops|stanz|core needle|entnahme", t):
            for did in build.fact_docs(f):
                for d in _fact_dates(build, f):
                    bio[did][d].append(f.get("id"))
    ok = "2016-04-11" in bio.get("12340016", {}) and "2016-04-12" in bio.get("12340018", {})
    R["checks"].append({
        "name": "Biopsy date 12340016 (11.04.2016) vs 12340018 (12.04.2016)",
        "ready": ok,
        "detail": "; ".join("%s: %s" % (did, ", ".join(sorted(v))) for did, v in sorted(bio.items())
                            if did in ("12340016", "12340018")) or "no dated biopsy facts",
        "fix": None if ok else
        "Extract a biopsy procedure fact from 12340016 (Entnahmedatum line, date 2016-04-11) and "
        "from 12340018 (ultrasound-guided biopsy sentence; date from its section heading, "
        "2016-04-12).",
    })

    # notes: suppression-worthy pairs and further candidates
    heights = []
    for f in build.facts:
        if _measure_kind(f) == "height":
            heights.append("%s=%s" % ("/".join(sorted(build.fact_docs(f))),
                                      _num_value(f, "größe|height")))
    R["notes"] += [
        "Do NOT flag: height 170 vs 171 cm across letters (measurement noise). Height facts: %s"
        % (", ".join(heights) or "none"),
        "Do NOT flag: weight 78 kg (06/2015) -> 67 kg (04.04.2016) -> 66 kg (04/2016): change "
        "over time; show as a trend (calculated loss ~12 kg is allowed if declared calculated).",
        "Do NOT flag: Blopress 1-0-1/2 (06/2015 discharge) vs 1-0-1 (04/2016 discharge): dose "
        "change over time.",
        "Do NOT flag: documents.json admission 2015-06-12 / discharge 2015-06-13 vs letter "
        "10.06.2015 / 14.06.2015 - differences from the JSON files are false alarms.",
        "Judgement call: 12340012 BP 'at admission' 140/90 vs 145/90 in the course text - small "
        "measurement difference, safer not to flag.",
        "Further real candidates (not checked): 12340018 discharge year typo (20156); 12340018 "
        "case number of the 2015 stay; 12340014 enlarged right axillary nodes vs 12340018 no "
        "enlarged axillary nodes / N0; 12340012 duplex paragraph sides swapped vs 12340008.",
    ]
    return R
