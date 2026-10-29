"""Generic comparison rules over the build artefacts (docs.json, passages.json, facts.json).

No document IDs, dates or answers are hard-coded here: everything is derived from the facts and
passages. Vocabulary (side words, weight-change words, stop words) is generic, not patient text.
"""
import collections
import difflib
import re

from pipeline.common import DATE_RE, SLASH_DATE_RE, find_dates, find_ws, iso, norm_ws

BMI_TOLERANCE = 1.0          # kg/m2: |stated - computed| above this is a contradiction
EVENT_WINDOW_DAYS = 7        # dates of the same event type closer than this belong to one event
COPY_SIMILARITY = 0.85       # difflib ratio above which two passages look copied
WEIGHT_CHANGE_MIN_KG = 2.0   # smaller changes are measurement noise

PLAN_STATUSES = {"planned", "recommended"}
SIDE_WORDS = {"left": "left", "right": "right", "bilateral": "bilateral",
              "links": "left", "rechts": "right", "li": "left", "re": "right", "bds": "bilateral"}
GENERIC_CATEGORIES = {"diagnosis", "procedure", "imaging", "therapy", "encounter", "presenting_event",
                      "attributed_cause"}
KEY_RESULT_CATEGORIES = {"lv_function", "hba1c", "carotid_stenosis", "histology", "receptor_status",
                         "ki67", "tnm", "egfr", "creatinine", "potassium"}
WEIGHT_CHANGE_WORDS = re.compile(r"gewichts(verlust|abnahme|reduktion|zunahme)|abgenommen|zugenommen|"
                                 r"weight (loss|gain)", re.I)
STOP = {"and", "the", "of", "in", "on", "by", "with", "for", "to", "a", "an", "at", "or", "during",
        "planned", "recommended", "regular", "further", "follow", "up", "follow-up", "next", "months",
        "month", "weeks", "week", "days", "day", "stay", "be", "is", "to", "after", "known", "history",
        "left", "right", "grade", "type", "ii", "i", "iii", "inpatient", "outpatient"}
HORMONE_RECEPTORS = {"ER", "PR", "HR"}   # oestrogen/progesterone receptors are summarised as hormone receptor
INTERVAL_RE = re.compile(r"(\d+)\s*(month|week|day)s?", re.I)


# --------------------------------------------------------------------------- build access
class Build:
    def __init__(self, docs, passages, facts):
        self.docs = docs
        self.passages = {p["id"]: p for p in passages}
        self.doc_passages = collections.defaultdict(list)
        for p in passages:
            self.doc_passages[p["doc_id"]].append(p)
        for v in self.doc_passages.values():
            v.sort(key=lambda p: p["start"])
        self.facts = facts
        self.fact = {f["id"]: f for f in facts}
        self.facts_on = collections.defaultdict(list)
        for f in facts:
            for pid in f["passage_ids"]:
                self.facts_on[pid].append(f)
        self.doc_order = sorted(docs, key=lambda d: (docs[d].get("date") or "", d))

    def doc_of(self, pid):
        return self.passages[pid]["doc_id"]

    def doc_date(self, doc_id):
        return self.docs[doc_id].get("date")

    def latest_doc(self):
        return self.doc_order[-1]

    def quote_in(self, quote, pid):
        """Exact substring of the passage text for `quote` (whitespace-tolerant lookup)."""
        text = self.passages[pid]["text"]
        if quote and quote in text:
            return quote
        span = find_ws(text, quote) if quote else None
        return text[span[0]:span[1]] if span else text

    def claim(self, fact, pid, asserted, quote=None):
        return {"fact_id": fact["id"], "passage_id": pid, "doc_id": self.doc_of(pid),
                "doc_date": self.doc_date(self.doc_of(pid)),
                "quote": self.quote_in(quote if quote is not None else fact["quote"], pid),
                "asserted": asserted}


# --------------------------------------------------------------------------- small helpers
def to_float(v):
    if v is None:
        return None
    m = re.search(r"\d+(?:[.,]\d+)?", str(v))
    return float(m.group(0).replace(",", ".")) if m else None


def parse_date(s):
    """ISO date from a dd.mm.yyyy / dd/mm/yyyy / '03. April 2016' string, or None (malformed)."""
    if not s:
        return None
    m = SLASH_DATE_RE.search(s)
    if m:
        return iso(m.group(1), m.group(2), m.group(3))
    d = find_dates(s)
    return d[0][0] if d else None


def days_between(a, b):
    import datetime
    da = datetime.date.fromisoformat(a)
    db = datetime.date.fromisoformat(b)
    return abs((db - da).days)


def add_interval(date_iso, n, unit):
    import datetime
    d = datetime.date.fromisoformat(date_iso)
    unit = unit.lower()
    if unit.startswith("day"):
        return (d + datetime.timedelta(days=n)).isoformat()
    if unit.startswith("week"):
        return (d + datetime.timedelta(weeks=n)).isoformat()
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return datetime.date(y, m, min(d.day, 28)).isoformat()


def stems(text):
    toks = re.findall(r"[a-zA-Zäöüß]+", (text or "").lower())
    return {t[:4] for t in toks if t not in STOP and len(t) >= 3}


def words(text):
    """Content words (full words, simple plural folding) for concept matching."""
    toks = re.findall(r"[a-zA-Zäöüß]+", (text or "").lower())
    return {t[:-1] if t.endswith("s") and len(t) > 4 else t for t in toks if t not in STOP and len(t) >= 3}


def fact_side(f, sided_categories=None):
    """Side from attrs.side; from the English label only for categories where other facts state a side."""
    s = (f.get("attrs") or {}).get("side")
    if s:
        return SIDE_WORDS.get(str(s).lower(), str(s).lower())
    if f["category"] in GENERIC_CATEGORIES or sided_categories is None or f["category"] not in sided_categories:
        return None
    words = set(re.findall(r"[a-z]+", f["label_en"].lower()))
    sides = {SIDE_WORDS[w] for w in words & {"left", "right", "bilateral"}}
    return sides.pop() if len(sides) == 1 else None


def is_plan(f):
    return f.get("status") in PLAN_STATUSES


# --------------------------------------------------------------------------- rule (a): BMI
def bmi_checks(b):
    """Every stated BMI recomputed from the nearest height + weight of the same document."""
    by_doc = collections.defaultdict(lambda: collections.defaultdict(list))
    for f in b.facts:
        if f["category"] in ("bmi", "height", "weight") and f["ips_section"] == "vital_signs":
            v = to_float(f["attrs"].get("value"))
            if v is None:
                continue
            for pid in f["passage_ids"]:
                by_doc[b.doc_of(pid)][f["category"]].append((f, pid, v, b.passages[pid]["start"]))
    checks = []
    for doc, cats in by_doc.items():
        for bf, bpid, bmi, bstart in cats.get("bmi", []):
            if not cats.get("height") or not cats.get("weight"):
                continue
            h = min(cats["height"], key=lambda x: abs(x[3] - bstart))
            w = min(cats["weight"], key=lambda x: abs(x[3] - bstart))
            hm = h[2] / 100.0 if h[2] > 3 else h[2]
            calc = round(w[2] / (hm * hm), 1)
            checks.append({"doc_id": doc, "date": b.doc_date(doc), "bmi": (bf, bpid, bmi),
                           "height": h, "weight": w, "computed": calc,
                           "mismatch": abs(calc - bmi) > BMI_TOLERANCE})
    checks.sort(key=lambda c: (c["date"] or "", c["doc_id"]))
    return checks


def rule_bmi(b):
    out = []
    checks = bmi_checks(b)
    for i, c in enumerate(checks):
        if not c["mismatch"]:
            continue
        bf, bpid, bmi = c["bmi"]
        hf, hpid, hv, _ = c["height"]
        wf, wpid, wv, _ = c["weight"]
        rationale = ("BMI recomputed from height and weight stated in the same document: "
                     "%g kg / (%.2f m)^2 = %.1f kg/m2; stated %g differs by %.1f (tolerance %.1f)."
                     % (wv, hv / 100.0, c["computed"], bmi, abs(c["computed"] - bmi), BMI_TOLERANCE))
        earlier = [e for e in checks[:i] if e["doc_id"] != c["doc_id"]
                   and abs(e["bmi"][2] - bmi) <= BMI_TOLERANCE and abs(e["computed"] - c["computed"]) > BMI_TOLERANCE]
        if earlier:
            e = earlier[-1]
            rationale += (" The stated value is close to the BMI %g stated in document %s (%s), when weight was %g kg: "
                          "possible copy error (value carried forward)." % (e["bmi"][2], e["doc_id"], e["date"], e["weight"][2]))
        out.append({
            "kind": "bmi_mismatch", "tier": "counted",
            "summary_en": "BMI %g stated, but %g kg at %g cm gives %.1f (document %s, %s)"
                          % (bmi, wv, hv, c["computed"], c["doc_id"], c["date"]),
            "rationale": rationale,
            "claims": [b.claim(bf, bpid, "BMI %g" % bmi), b.claim(hf, hpid, "height %g cm" % hv),
                       b.claim(wf, wpid, "weight %g kg" % wv)],
            "_chain": ("bmi", None)})
    return out


# --------------------------------------------------------------------------- rule (b): laterality
def sided_claims(b):
    groups = collections.defaultdict(list)
    sided_cats = {f["category"] for f in b.facts if (f.get("attrs") or {}).get("side")}
    for f in b.facts:
        if is_plan(f):
            continue
        side = fact_side(f, sided_cats)
        if side not in ("left", "right"):
            continue
        for pid in f["passage_ids"]:
            groups[f["category"]].append({"fact": f, "pid": pid, "side": side,
                                          "doc": b.doc_of(pid), "section": b.passages[pid]["section"]})
    return groups


def copy_suspects(b, pid):
    """Earlier passages with near-identical wording (possible copy source)."""
    text = b.passages[pid]["text"]
    date = b.doc_date(b.doc_of(pid)) or ""
    out = []
    for q in b.passages.values():
        if q["doc_id"] == b.doc_of(pid) or (b.doc_date(q["doc_id"]) or "") > date or len(q["text"]) < 30:
            continue
        r = difflib.SequenceMatcher(None, text, q["text"]).ratio()
        if COPY_SIMILARITY <= r < 1.0:
            out.append((r, q["id"]))
    return [pid2 for _, pid2 in sorted(out, reverse=True)]


def rule_laterality(b):
    conflicts = []
    for cat, cl in sided_claims(b).items():
        sides = collections.Counter()
        seen = set()
        for c in cl:
            if (c["pid"], c["side"]) not in seen:
                seen.add((c["pid"], c["side"]))
                sides[c["side"]] += 1
        if len(sides) < 2:
            continue
        (s1, n1), (s2, n2) = sides.most_common(2)
        minority = [c for c in cl if n1 == n2 or c["side"] != s1]
        conflicts.append({"cats": [cat], "claims": cl, "loci": {(c["doc"], c["section"]) for c in minority},
                          "majority": None if n1 == n2 else s1, "weight": n1 + n2})
    # merge conflicts that share the locus of their odd claims (e.g. one mirrored paragraph)
    merged = []
    for c in sorted(conflicts, key=lambda x: (x["majority"] is None, -x["weight"])):
        for m in merged:
            if m["loci"] & c["loci"]:
                m["cats"] += c["cats"]
                m["claims"] += c["claims"]
                m["loci"] |= c["loci"]
                break
        else:
            c["main_loci"] = set(c["loci"])
            merged.append(c)
    out = []
    for m in merged:
        main = m["cats"][0]
        main_claims = [c for c in m["claims"] if c["fact"]["category"] == main]
        maj = m["majority"]
        odd = [c for c in main_claims if maj and c["side"] != maj]
        docs_odd = sorted({c["doc"] for c in odd})
        within = [d for d in docs_odd if any(c["doc"] == d and c["side"] == maj for c in main_claims)]
        cnt = collections.Counter(c["side"] for c in main_claims)
        if maj:
            summary = "%s: %s in %s vs %s in %d other passage(s)%s" % (
                main.replace("_", " ").capitalize(), odd[0]["side"].upper(),
                ", ".join(sorted({c["pid"] for c in odd})), maj.upper(), cnt[maj],
                " (incl. the same document)" if within else "")
        else:
            summary = "%s: side differs - %s" % (main.replace("_", " ").capitalize(),
                                                  " vs ".join("%s in %d passage(s)" % (s, n) for s, n in cnt.most_common()))
        rationale = ("Same anatomical structure (%s) is reported on different sides." % ", ".join(m["cats"]))
        if maj:
            rationale += " Majority side: %s; odd side in document(s) %s." % (maj, ", ".join(docs_odd))
        if within:
            rationale += " Document(s) %s contradict themselves (both sides in one document)." % ", ".join(within)
        copies = []
        for c in odd:
            for src in copy_suspects(b, c["pid"])[:1]:
                copies.append("passage %s is near-identical to earlier passage %s except for the side: possible copy error"
                              % (c["pid"], src))
        if copies:
            rationale += " " + "; ".join(sorted(set(copies))) + "."
        if len(m["cats"]) > 1:
            rationale += " Related findings (%s) are mirrored in the same passages and are counted once here." % ", ".join(m["cats"][1:])
        claims, seen = [], set()
        for c in sorted(m["claims"], key=lambda c: (b.doc_date(c["doc"]) or "", c["pid"])):
            if (c["fact"]["id"], c["pid"]) in seen:
                continue
            seen.add((c["fact"]["id"], c["pid"]))
            claims.append(b.claim(c["fact"], c["pid"], "%s: %s" % (c["fact"]["category"], c["side"])))
        out.append({"kind": "laterality", "tier": "counted", "summary_en": summary, "rationale": rationale,
                    "claims": claims, "_chain": ("side", (tuple(m["cats"]), frozenset(m["main_loci"])))})
    out += rule_finding_side_notes(b)
    return out


def rule_finding_side_notes(b):
    """Same structure, different finding, only one side stated -> laterality to check (not counted)."""
    out = []
    groups = collections.defaultdict(list)
    for f in b.facts:
        if not is_plan(f) and f["attrs"].get("finding"):
            groups[f["category"]].append(f)
    for cat, fl in groups.items():
        findings = {f["attrs"]["finding"] for f in fl}
        sided = [f for f in fl if fact_side(f)]
        unsided = [f for f in fl if not fact_side(f)]
        if len(findings) < 2 or not sided or not unsided:
            continue
        fl = sorted(fl, key=lambda f: (f["date"] or "", f["id"]))
        desc = "; ".join("%s (%s)" % (f["label_en"], f["date"]) for f in fl)
        out.append({
            "kind": "laterality_to_check", "tier": "documentation_note",
            "summary_en": "%s: laterality to check - %s" % (cat.replace("_", " "), desc),
            "rationale": ("Findings for the same structure differ and only some state a side. Different methods/dates "
                          "can explain a real change, so this is not counted as a contradiction; the stated side "
                          "should be checked."),
            "claims": [b.claim(f, f["passage_ids"][0], "%s%s" % (f["attrs"]["finding"],
                                                               ", side " + fact_side(f) if fact_side(f) else ", side not stated"))
                       for f in fl],
            "_chain": ("finding", cat)})
    return out


# --------------------------------------------------------------------------- rule (c): event dates
def heading_date(b, pid):
    """Date of the parent heading of a passage (e.g. 'Examination of <date>:'), as (iso, heading_pid)."""
    p = b.passages[pid]
    seq = b.doc_passages[p["doc_id"]]
    idx = next(i for i, q in enumerate(seq) if q["id"] == pid)
    for q in reversed(seq[:idx]):
        t = q["text"].strip()
        if not t.endswith(":"):
            continue
        if p["section"] and t == p["section"].strip():
            continue
        d = find_dates(t)
        return (d[0][0], q["id"]) if d else (None, None)
    return None, None


def event_claims(b):
    """(event_type, iso_or_None, raw, fact, pid, planned, quote_override)."""
    ev = []
    for f in b.facts:
        a = f.get("attrs") or {}
        pid = f["passage_ids"][0]
        if f["category"] == "encounter":
            for key in ("admission", "discharge"):
                if a.get(key):
                    ev.append((key, parse_date(a[key]), a[key], f, pid, False, None))
            if a.get("event") in ("admission", "discharge") and a.get("date_text"):
                ev.append((a["event"], parse_date(a["date_text"]), a["date_text"], f, pid, False, None))
        elif f["category"] == "planned_admission":
            d = parse_date(f["quote"])
            if d:
                ev.append(("admission", d, d, f, pid, True, None))
        elif f["category"] == "biopsy" and not is_plan(f):
            d = parse_date(a.get("date_text")) or parse_date(f["quote"])
            if d:
                ev.append(("biopsy", d, a.get("date_text") or d, f, pid, False, None))
            else:
                hd, hpid = heading_date(b, pid)
                if hd:
                    hf = (b.facts_on.get(hpid) or [f])[0]
                    ev.append(("biopsy", hd, b.passages[hpid]["text"], f, pid, False, None))
                    ev.append(("biopsy", hd, b.passages[hpid]["text"], hf, hpid, False, b.passages[hpid]["text"]))
    return ev


def cluster_events(ev):
    clusters = []
    for e in sorted([e for e in ev if e[1]], key=lambda e: e[1]):
        if clusters and clusters[-1]["type"] == e[0] and days_between(clusters[-1]["last"], e[1]) <= EVENT_WINDOW_DAYS:
            clusters[-1]["items"].append(e)
            clusters[-1]["last"] = e[1]
        else:
            clusters.append({"type": e[0], "items": [e], "last": e[1]})
    return clusters


def rule_event_dates(b):
    ev = event_claims(b)
    out = []
    by_type = collections.defaultdict(list)
    for e in ev:
        by_type[e[0]].append(e)
    for etype, items in sorted(by_type.items()):
        for cl in cluster_events(items):
            actual = [e for e in cl["items"] if not e[5]]
            dates = sorted({e[1] for e in actual})
            if len(dates) < 2:
                continue
            docs = sorted({b.doc_of(e[4]) for e in actual})
            claims = [b.claim(e[3], e[4], "%s on %s" % (etype, e[1]), e[6]) for e in actual]
            planned = [e for e in cl["items"] if e[5]]
            rationale = ("The same %s (dates within %d days, same episode) is given %d different dates: %s."
                         % (etype, EVENT_WINDOW_DAYS, len(dates), ", ".join(dates)))
            if len(docs) == 1:
                rationale += " Both dates are in the same document %s." % docs[0]
            if planned:
                rationale += " Previously planned for %s (document %s) - context only, plans may change." % (
                    planned[0][1], b.doc_of(planned[0][4]))
            out.append({"kind": "event_date", "tier": "counted",
                        "summary_en": "%s date differs: %s" % (etype.capitalize(), " vs ".join(dates)),
                        "rationale": rationale, "claims": claims, "_chain": ("event", (etype, cl["items"][0][1]))})
    # malformed dates -> documentation note, linked to a valid date for the same event in the same doc
    for e in ev:
        if e[1] is None and not e[5]:
            same = [x for x in ev if x[0] == e[0] and x[1] and b.doc_of(x[4]) == b.doc_of(e[4])]
            claims = [b.claim(e[3], e[4], "%s written as '%s' (not a valid date)" % (e[0], e[2]))]
            claims += [b.claim(x[3], x[4], "%s on %s" % (x[0], x[1])) for x in same]
            out.append({"kind": "malformed_date", "tier": "documentation_note",
                        "summary_en": "%s date written as '%s' is not a valid date%s" % (
                            e[0].capitalize(), e[2], (" (elsewhere in the document: %s)" % same[0][1]) if same else ""),
                        "rationale": "Typing error in a date; the intended date is probably the valid one in the same "
                                     "document. Not counted as a contradiction.",
                        "claims": claims, "_chain": None})
    return out


# --------------------------------------------------------------------------- rule (d): case numbers
def stays(b):
    """Inpatient stays derived from admission/discharge facts: [{start, end, letter_docs}]."""
    per_doc = collections.defaultdict(lambda: {"admission": [], "discharge": []})
    for e in event_claims(b):
        if e[1] and not e[5] and e[0] in ("admission", "discharge"):
            per_doc[b.doc_of(e[4])][e[0]].append(e[1])
    out = []
    for doc, d in per_doc.items():
        if d["admission"] and d["discharge"]:
            out.append({"start": min(d["admission"]), "end": max(d["discharge"]), "letter": doc})
    return sorted(out, key=lambda s: s["start"])


def rule_case_numbers(b):
    cases = collections.defaultdict(list)
    for f in b.facts:
        if f["category"] == "case_number":
            for pid in f["passage_ids"]:
                cases[b.doc_of(pid)].append((f, pid))
    out = []
    st = stays(b)

    def members(s):
        return [d for d in b.docs if d == s["letter"] or s["start"] <= (b.doc_date(d) or "") <= s["end"]]

    for s in st:
        nums = collections.defaultdict(list)
        for d in members(s):
            for f, pid in cases.get(d, []):
                nums[f["attrs"]["value"]].append((f, pid))
        if len(nums) < 2:
            continue
        rationale = ("Documents of the same stay (%s to %s) carry %d different case numbers."
                     % (s["start"], s["end"], len(nums)))
        for n in sorted(nums):
            docs_n = {d for d, lst in cases.items() if any(f["attrs"]["value"] == n for f, _ in lst)}
            other = [x for x in st if x is not s and docs_n & set(members(x))]
            if other:
                rationale += " Case number %s is also used for the stay %s to %s." % (n, other[0]["start"], other[0]["end"])
        claims = []
        for n in sorted(nums):
            for f, pid in nums[n]:
                claims.append(b.claim(f, pid, "case number %s" % n))
        out.append({"kind": "case_number_mismatch", "tier": "documentation_note",
                    "summary_en": "Case numbers differ within one stay: %s" % " vs ".join(sorted(nums)),
                    "rationale": rationale + " Administrative inconsistency, not counted as a clinical contradiction.",
                    "claims": claims, "_chain": None})
    return out


# --------------------------------------------------------------------------- not flagged (transparency)
def not_flagged(b):
    """Differences deliberately NOT reported: small measurement variation, change over time, dose changes."""
    out = []
    num = collections.defaultdict(list)
    for f in b.facts:
        if f["ips_section"] == "vital_signs" and to_float(f["attrs"].get("value")) is not None and "/" not in str(f["attrs"].get("value")):
            num[(f["category"], f["attrs"].get("context"))].append(f)
    for (cat, ctx), fl in sorted(num.items(), key=lambda x: (x[0][0], str(x[0][1]))):
        vals = sorted({to_float(f["attrs"]["value"]) for f in fl})
        if len(vals) > 1:
            out.append({"category": cat, "values": vals, "fact_ids": [f["id"] for f in fl],
                        "reason": "values from different dates: change over time or measurement variation"})
    bp = collections.defaultdict(list)
    for f in b.facts:
        if f["category"] == "blood_pressure":
            bp[b.doc_of(f["passage_ids"][0])].append(f)
    for doc, fl in bp.items():
        vals = sorted({f["attrs"]["value"] for f in fl})
        if len(vals) > 1:
            out.append({"category": "blood_pressure", "values": vals, "fact_ids": [f["id"] for f in fl],
                        "reason": "different measurement moments (pre-hospital, on admission, after treatment, means)"})
    meds = collections.defaultdict(list)
    for f in b.facts:
        if f["ips_section"] == "medications" and f["attrs"].get("schedule"):
            meds[f["attrs"].get("generic")].append(f)
    for g, fl in sorted(meds.items(), key=lambda x: str(x[0])):
        sched = sorted({(f["attrs"].get("dose"), f["attrs"]["schedule"]) for f in fl})
        if len(sched) > 1 and len({f["date"] for f in fl}) > 1:
            out.append({"category": "medication", "values": ["%s %s" % s for s in sched],
                        "fact_ids": [f["id"] for f in fl], "reason": "%s: dose/schedule changed over time" % g})
    return out


# --------------------------------------------------------------------------- blind spots
def concept_key(f):
    if f["ips_section"] == "medications":
        return "med:" + str(f["attrs"].get("generic") or f["label_en"].lower())
    if f["ips_section"] == "allergies":
        return "allergy:" + str(f["attrs"].get("substance") or f["label_en"].lower())
    if f["category"] == "receptor_status":
        r = str(f["attrs"].get("receptor"))
        return "receptor:" + ("HR" if r in HORMONE_RECEPTORS else r)
    if f["category"] not in GENERIC_CATEGORIES:
        return "cat:" + f["category"]
    if f.get("code"):
        return "%s:%s" % (f["code"]["system"], f["code"]["value"])
    return "label:" + norm_ws(f["label_en"].lower())


def is_important(f):
    a = f.get("attrs") or {}
    if is_plan(f):
        return False
    if f["ips_section"] == "allergies":
        return True
    if f["ips_section"] == "medications":
        return bool(a.get("schedule") or a.get("schedule_mo_mi_ab_na") or a.get("frequency"))
    if f["ips_section"] in ("problems", "past_illness") and f["category"] not in ("encounter", "case_number"):
        if a.get("assertion") in ("negative", "suspected"):
            return False
        return a.get("context") in ("diagnosis list", "diagnosis") or f["category"] not in GENERIC_CATEGORIES
    if f["ips_section"] == "results":
        return f["category"] in KEY_RESULT_CATEGORIES
    return False


def same_concept(f, g):
    if concept_key(f) == concept_key(g):
        return True
    if f["ips_section"] in ("medications", "allergies") or g["ips_section"] in ("medications", "allergies"):
        return False
    if not (concept_key(f).startswith("label:") or concept_key(g).startswith("label:")):
        return False      # both coded / categorised differently -> different concepts
    sf, sg = words(f["label_en"]), words(g["label_en"])
    if not sf or not sg:
        return False
    small = min(len(sf), len(sg))
    return len(sf & sg) >= min(2, small) and len(sf & sg) * 2 >= small


def blind_spots(b):
    latest = b.latest_doc()
    latest_facts = [f for f in b.facts if any(b.doc_of(p) == latest for p in f["passage_ids"])]
    concepts = collections.OrderedDict()
    for f in sorted(b.facts, key=lambda f: (f["date"] or "", f["id"])):
        if not is_important(f):
            continue
        k = concept_key(f)
        concepts.setdefault(k, []).append(f)
    # merge label/code concepts that are the same thing under different keys
    keys = list(concepts)
    merged = collections.OrderedDict()
    for k in keys:
        target = next((m for m in merged if same_concept(concepts[k][0], merged[m][0])), None)
        if target:
            merged[target] += concepts[k]
        else:
            merged[k] = list(concepts[k])
    out = []
    present = 0
    for k, fl in merged.items():
        in_latest = any(any(b.doc_of(p) == latest for p in f["passage_ids"]) for f in fl) or \
            any(same_concept(f, g) for f in fl[:1] for g in latest_facts)
        if in_latest:
            present += 1
            continue
        claims = [(f, p) for f in fl for p in f["passage_ids"]]
        claims.sort(key=lambda x: (b.doc_date(b.doc_of(x[1])) or "", x[1]))
        lf, lp = claims[-1]
        out.append({"kind": "dropped_from_latest", "concept": k,
                    "label_en": min((f["label_en"] for f in fl), key=lambda l: ("left" not in l and "right" not in l
                                                                                and "bilateral" not in l, len(l))),
                    "ips_section": fl[0]["ips_section"], "category": fl[0]["category"],
                    "last_seen_doc": b.doc_of(lp), "last_seen_date": b.doc_date(b.doc_of(lp)),
                    "first_seen_date": b.doc_date(b.doc_of(claims[0][1])),
                    "fact_ids": sorted({f["id"] for f in fl}),
                    "passage_ids": sorted({p for _, p in claims}),
                    "claims": [b.claim(f, p, f["label_en"]) for f, p in claims]})
    computed = weight_change(b)
    return out, computed, {"latest_doc": latest, "latest_date": b.doc_date(latest),
                           "important_concepts": len(merged), "present_in_latest": present,
                           "missed_if_only_latest_read": len(out)}


def weight_change(b):
    w = []
    for f in b.facts:
        if f["category"] == "weight" and f["ips_section"] == "vital_signs" and to_float(f["attrs"].get("value")):
            for pid in f["passage_ids"]:
                w.append((b.doc_date(b.doc_of(pid)), f, pid, to_float(f["attrs"]["value"])))
    w.sort(key=lambda x: (x[0] or "", x[2]))
    if len(w) < 2:
        return []
    first, last = w[0], w[-1]
    delta = last[3] - first[3]
    if abs(delta) < WEIGHT_CHANGE_MIN_KG:
        return []
    stated = [d for d in b.docs if WEIGHT_CHANGE_WORDS.search(b.docs[d].get("display_text", ""))]
    pct = 100.0 * delta / first[3]
    return [{"kind": "unstated_computed", "concept": "computed:weight_change",
             "label_en": "Weight change %g kg -> %g kg (%+g kg, %+.1f%%) between %s and %s"
                         % (first[3], last[3], delta, pct, first[0], last[0]),
             "value": {"from_kg": first[3], "to_kg": last[3], "delta_kg": delta, "delta_pct": round(pct, 1),
                       "from_date": first[0], "to_date": last[0]},
             "calculated": True, "stated_in_documents": stated,
             "note": ("No document states this change." if not stated else "Change mentioned in: " + ", ".join(stated)),
             "last_seen_doc": b.doc_of(last[2]), "last_seen_date": last[0],
             "fact_ids": [x[1]["id"] for x in w], "passage_ids": [x[2] for x in w],
             "claims": [b.claim(x[1], x[2], "weight %g kg on %s" % (x[3], x[0])) for x in w]}]


# --------------------------------------------------------------------------- open follow-ups
def followup_terms(f):
    a = f.get("attrs") or {}
    src = a.get("test") or " ".join(a.get("procedures") or []) or f["label_en"]
    return stems(src)


def open_followups(b):
    plans = [f for f in b.facts if is_plan(f) and len(f["quote"].split()) >= 3]
    # merge the same recommendation repeated across documents
    groups = []
    for f in sorted(plans, key=lambda f: (b.doc_date(b.doc_of(f["passage_ids"][0])) or "", f["id"])):
        t = followup_terms(f)
        for g in groups:
            gt = g["terms"]
            if t and gt and len(t & gt) * 2 > max(len(t), len(gt)) and g["status"] == f["status"]:
                g["facts"].append(f)
                break
        else:
            groups.append({"terms": t, "facts": [f], "status": f["status"]})
    last_date = b.doc_date(b.latest_doc())
    out = []
    for i, g in enumerate(groups, 1):
        f0 = g["facts"][-1]
        authored_doc = b.doc_of(f0["passage_ids"][0])
        authored = b.doc_date(authored_doc)
        plan_docs = {b.doc_of(p) for f in g["facts"] for p in f["passage_ids"]}
        terms = g["terms"]
        need = min(2, len(terms))
        evidence, scheduled = [], []
        for h in b.facts:
            if h in g["facts"] or not terms:
                continue
            hdocs = {b.doc_of(p) for p in h["passage_ids"]}
            hit = len(stems(h["label_en"]) & terms)
            if hit < need:
                continue
            if not (hdocs & plan_docs) and (b.doc_date(sorted(hdocs)[0]) or "") > authored:
                evidence.append(h)
            elif authored_doc in hdocs and is_plan(h) and (h["date"] or "") > authored:
                scheduled.append(h)
        due = None
        m = INTERVAL_RE.search(f0["quote"]) or INTERVAL_RE.search(" ".join(str(v) for v in f0["attrs"].values()))
        if m:
            due = add_interval(authored, int(m.group(1)), m.group(2))
        elif f0["status"] == "planned" and f0["date"] and f0["date"] > authored:
            due = f0["date"]
        recurring = bool(re.search(r"\bregular", f0["label_en"], re.I))
        done = [h for h in evidence if not is_plan(h)]
        if done and recurring:
            resolution = "recurring_some_evidence"
        elif done:
            resolution = "completed"
        elif evidence:
            resolution = "superseded_by_later_plan"
        elif scheduled:
            resolution = "scheduled"
            due = due or min(h["date"] for h in scheduled)
        elif due and due > last_date:
            resolution = "pending_due_after_last_document"
        else:
            resolution = "open"
        later_docs = [d for d in b.doc_order if (b.doc_date(d) or "") > authored]
        searched_secs = sorted({h["ips_section"] for h in b.facts if any(b.doc_of(p) in later_docs for p in h["passage_ids"])})
        out.append({
            "id": "fu%02d" % i, "label_en": f0["label_en"], "status": f0["status"],
            "authored_doc": authored_doc, "authored_date": authored, "due": due, "recurring": recurring,
            "resolution": resolution, "is_open": resolution in ("open",),
            "fact_ids": [f["id"] for f in g["facts"]],
            "passage_ids": [p for f in g["facts"] for p in f["passage_ids"]],
            "claims": [b.claim(f, p, f["label_en"]) for f in g["facts"] for p in f["passage_ids"]],
            "evidence": [b.claim(h, h["passage_ids"][0], "%s (%s, %s)" % (h["label_en"], h["status"], h["date"]))
                         for h in sorted(evidence + scheduled, key=lambda h: (h["date"] or "", h["id"]))],
            "searched": "searched: categories %s for terms [%s] in %d document(s) dated after %s (%s)" % (
                ", ".join(searched_secs) or "none", ", ".join(sorted(terms)), len(later_docs), authored,
                ", ".join(later_docs) or "none")})
    return out


# --------------------------------------------------------------------------- propagation (feature 6)
def propagation(b, contradiction):
    """Ordered chain (by document date) of how a conflicting fact appears across documents."""
    kind, key = contradiction.get("_chain") or (None, None)
    if not kind:
        return None
    entries = []          # (doc, pid, value, extra)
    refs = {}
    if kind == "side":
        cats, loci = key
        sc = sided_claims(b)
        for cat in cats:
            cl = sc.get(cat, [])
            for c in cl:
                entries.append((c["doc"], c["pid"], c["side"], cat))
            # reference side: majority among passages outside the loci of the odd (mirrored) claims
            outside = collections.Counter(c["side"] for c in cl if (c["doc"], c["section"]) not in loci)
            refs[cat] = outside.most_common(1)[0][0] if outside else None
    elif kind == "bmi":
        for c in bmi_checks(b):
            bf, bpid, bmi = c["bmi"]
            entries.append((c["doc_id"], bpid, "stated %g / computed %.1f" % (bmi, c["computed"]),
                            "conflicting" if c["mismatch"] else "consistent"))
    elif kind == "event":
        etype, anchor = key
        for cl in cluster_events([e for e in event_claims(b) if e[0] == etype]):
            if cl["items"][0][1] == anchor:
                for e in cl["items"]:
                    entries.append((b.doc_of(e[4]), e[4], e[1], "planned" if e[5] else "stated"))
    elif kind == "finding":
        for f in b.facts:
            if f["category"] == key and f["attrs"].get("finding") and not is_plan(f):
                entries.append((b.doc_of(f["passage_ids"][0]), f["passage_ids"][0],
                                "%s%s" % (f["attrs"]["finding"], (", " + fact_side(f)) if fact_side(f) else ""), None))
    if not entries:
        return None
    first_date = min(b.doc_date(e[0]) or "" for e in entries)
    stated_values = {e[2] for e in entries if not (kind == "event" and e[3] == "planned")}
    chain = []
    for doc in b.doc_order:
        if (b.doc_date(doc) or "") < first_date:
            continue
        mine = [e for e in entries if e[0] == doc]
        if not mine:
            chain.append({"doc_id": doc, "date": b.doc_date(doc), "value": None, "passage_id": None,
                          "status": "absent", "note": "not mentioned in this document"})
            continue
        seen = set()
        for e in sorted(mine, key=lambda e: b.passages[e[1]]["start"]):
            if (e[1], e[2], e[3]) in seen:
                continue
            seen.add((e[1], e[2], e[3]))
            if kind == "bmi":
                status = e[3]
            elif kind == "side":
                status = "consistent" if refs.get(e[3]) in (None, e[2]) else "conflicting"
            else:   # dates / findings: no version is assumed correct
                status = "conflicting" if len(stated_values) > 1 else "consistent"
            item = {"doc_id": doc, "date": b.doc_date(doc), "value": e[2], "passage_id": e[1], "status": status}
            if kind == "side":
                item["structure"] = e[3]
                if status == "conflicting":
                    src = copy_suspects(b, e[1])
                    if src:
                        item["note"] = ("possible copy error: wording near-identical to %s (%s) except the side"
                                        % (src[0], b.doc_date(b.doc_of(src[0]))))
            if kind == "event" and e[3] == "planned":
                item["status"] = "consistent" if e[2] in stated_values else "conflicting"
                item["note"] = "planned date (context only)"
            chain.append(item)
    out = {"kind": kind, "chain": chain}
    if kind == "side":
        out["reference_value"] = refs
    return out


# --------------------------------------------------------------------------- assemble
def compare(docs, passages, facts):
    b = Build(docs, passages, facts)
    contradictions = rule_laterality(b) + rule_bmi(b) + rule_event_dates(b) + rule_case_numbers(b)
    contradictions.sort(key=lambda c: (c["tier"] != "counted", c["kind"], c["claims"][0]["doc_date"] or ""))
    prop, by_key = [], {}
    for i, c in enumerate(contradictions, 1):
        c["id"] = "c%02d" % i
        k = repr(c.get("_chain"))
        if c.get("_chain") and k in by_key:
            by_key[k]["contradiction_ids"].append(c["id"])
        else:
            p = propagation(b, c)
            if p:
                p["contradiction_ids"] = [c["id"]]
                p["summary_en"] = c["summary_en"] if c["kind"] != "bmi_mismatch" else "BMI stated vs recomputed per document"
                by_key[k] = p
                prop.append(p)
        c.pop("_chain", None)
    contradictions = [dict([("id", c["id"])] + [(k, v) for k, v in c.items() if k != "id"]) for c in contradictions]
    dropped, computed, bs_counts = blind_spots(b)
    for i, x in enumerate(dropped + computed, 1):
        x["id"] = "bs%02d" % i
    fus = open_followups(b)
    counts = {
        "contradictions_counted": sum(c["tier"] == "counted" for c in contradictions),
        "documentation_notes": sum(c["tier"] == "documentation_note" for c in contradictions),
        "blind_spots": len(dropped) + len(computed),
        "open_followups": sum(f["is_open"] for f in fus),
        "followups_total": len(fus),
    }
    counts.update(bs_counts)
    return {"counts": counts, "contradictions": contradictions,
            "blind_spots": dropped + computed, "open_followups": fus,
            "propagation": prop, "not_flagged": not_flagged(b)}
