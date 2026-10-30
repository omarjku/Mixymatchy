"""Fill: one need row (rulebook) -> one answer card.

Card statuses (the four reliability marks plus n/a):
  consistent      facts found, the documents agree
  conflicting     a counted contradiction touches the card's facts
  outdated        only old information (latest value older than ~6 months before as_of)
  not_documented  nothing in the 8 documents; decided by the computer, never guessed
  not_applicable  the need does not apply to this patient (applies_if)
"""
import datetime
import re

DATE_FMT = "%Y-%m-%d"


# ----------------------------------------------------------------- helpers

def _d(s):
    try:
        return datetime.datetime.strptime(str(s)[:10], DATE_FMT).date()
    except (TypeError, ValueError):
        return None


def fmt_date(s, precision="day"):
    d = _d(s)
    if not d:
        return s or ""
    if precision == "month":
        return d.strftime("%m/%Y")
    if precision == "year":
        return str(d.year)
    return d.strftime("%d.%m.%Y")


def _flat(attrs):
    out = []
    if isinstance(attrs, dict):
        for k, v in attrs.items():
            if k in ("confirmed_by_ibm",):
                continue
            out.extend(_flat(v))
    elif isinstance(attrs, (list, tuple)):
        for v in attrs:
            out.extend(_flat(v))
    elif isinstance(attrs, str):
        out.append(attrs)
    return out


def fact_text(f):
    """English, on-screen text of a fact (label + attribute values); never the German quote."""
    return (f.get("label_en") or "") + " | " + " ".join(_flat(f.get("attrs") or {}))


def _key(label):
    return re.sub(r"[\s.,;:]+", " ", (label or "").lower()).strip()


def _date_after(fact, threshold):
    """True only if the fact is definitely after threshold, at the fact's date precision."""
    d = str(fact.get("date") or "")
    prec = fact.get("date_precision") or "day"
    if not d:
        return False
    if prec == "year":
        return d[:4] > threshold[:4]
    if prec == "month":
        return d[:7] > threshold[:7]
    return d[:10] > threshold[:10]


def _older_than(date, as_of, days):
    a, b = _d(date), _d(as_of)
    return bool(a and b and (b - a).days > days)


# ----------------------------------------------------------------- selection

def select(store, need, as_of):
    cats = need.get("category") or []
    if isinstance(cats, str):
        cats = [cats]
    all_meds = "medications:*" in cats
    match = re.compile(need["match"], re.I) if need.get("match") else None
    match_all = [re.compile(x, re.I) for x in need.get("match_all") or []]
    exclude = re.compile(need["exclude"], re.I) if need.get("exclude") else None
    status_in = set(need.get("status_in") or [])
    out = []
    for f in store.facts:
        if all_meds:
            if f.get("ips_section") != "medications":
                continue
        elif f.get("category") not in cats:
            continue
        t = fact_text(f)
        if match and not match.search(t):
            continue
        if any(not rx.search(t) for rx in match_all):
            continue
        if exclude and exclude.search(t):
            continue
        if status_in and f.get("status") not in status_in:
            continue
        if f.get("status") not in ("planned", "recommended") and str(f.get("date") or "")[:10] > as_of:
            continue
        out.append(f)
    # a 'question: X?' / suspected fact adds nothing when a positive fact exists
    pos = [f for f in out if (f.get("attrs") or {}).get("assertion") != "suspected"]
    return pos if pos else out


def group_items(store, facts):
    """Group facts with the same English label (the same statement in several letters)."""
    items = {}
    for f in sorted(facts, key=lambda x: (str(x.get("date") or ""), x["id"])):
        k = _key(f.get("label_en"))
        it = items.get(k)
        if it is None:
            it = items[k] = {"label_en": f.get("label_en"), "date": f.get("date"), "first_date": f.get("date"),
                             "date_precision": f.get("date_precision") or "day", "status": f.get("status"),
                             "facts": [], "docs": [], "passages": []}
        it["facts"].append(f["id"])
        if str(f.get("date") or "") >= str(it["date"] or ""):
            it["date"], it["status"] = f.get("date"), f.get("status")
            it["date_precision"] = f.get("date_precision") or "day"
        for d in store.fact_docs(f):
            if d not in it["docs"]:
                it["docs"].append(d)
        for p in f.get("passage_ids") or []:
            if p not in it["passages"]:
                it["passages"].append(p)
    return list(items.values())


def _with_date(it):
    return "%s (%s)" % (it["label_en"], fmt_date(it["date"], it.get("date_precision")))


# ----------------------------------------------------------------- not documented

def _search_passages(store, need):
    terms = need.get("search_terms") or []
    hits = []
    for rx in terms:
        r = re.compile(rx, re.I)
        for p in store.passages:
            if r.search(p.get("text") or "") and p["id"] not in hits:
                hits.append(p["id"])
    return hits


def not_documented(store, need, card, extra=""):
    cats = need.get("category") or []
    mentions = _search_passages(store, need)
    card["status"] = "not_documented"
    card["searched"] = {
        "documents": len(store.docs),
        "facts_checked": len(store.facts),
        "categories": cats,
        "match": need.get("match") or need.get("match_all"),
        "terms": need.get("search_terms") or [],
        "passages_scanned": len(store.passages) if need.get("search_terms") else 0,
        "possible_mentions": mentions[:5],
    }
    if mentions:
        card["value_en"] = ("No extracted fact; %d passage(s) contain a search term - open the source to check%s"
                            % (len(mentions), extra))
        card["passages"] = mentions[:5]
    else:
        card["value_en"] = "Not documented in any of the %d documents%s" % (len(store.docs), extra)
    return card


# ----------------------------------------------------------------- compute types

def _list(store, need, card, facts, as_of, outdated_days):
    items = group_items(store, facts)
    if not items:
        return not_documented(store, need, card)
    items.sort(key=lambda it: str(it["date"] or ""), reverse=True)
    card["items"] = items
    shown = items[:10]
    more = len(items) - len(shown)
    card["value_en"] = "; ".join(it["label_en"] for it in shown) + (" (+%d more)" % more if more > 0 else "")
    card["date"] = items[0]["date"]
    card["status"] = "consistent"
    max_age = need.get("max_age_days")
    if max_age and all(it["status"] not in ("planned", "recommended") for it in items) \
            and _older_than(card["date"], as_of, max_age):
        card["status"] = "outdated"
        card["note"] = "Latest entry from %s; nothing newer documented." % fmt_date(card["date"])
    return card


def _latest(store, need, card, facts, as_of, outdated_days):
    if not facts:
        return not_documented(store, need, card)
    items = group_items(store, facts)
    rank = lambda it: (str(it["date"] or ""), it["status"] == "current", max(it["docs"] or [""]))
    items.sort(key=rank, reverse=True)
    top = items[0]
    card["items"] = [top]
    card["earlier"] = [{"label_en": it["label_en"], "date": it["date"], "facts": it["facts"],
                        "passages": it["passages"]} for it in items[1:4]]
    card["value_en"] = _with_date(top)
    card["date"] = top["date"]
    card["status"] = "consistent"
    if top["status"] not in ("planned", "recommended") and _older_than(top["date"], as_of,
                                                                        need.get("max_age_days") or outdated_days):
        card["status"] = "outdated"
        card["note"] = "Only measured %s; no later value documented." % fmt_date(top["date"], top.get("date_precision"))
    return card


def _value(f):
    v = (f.get("attrs") or {}).get("value")
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        m = re.search(r"\d+(?:[.,]\d+)?", f.get("label_en") or "")
        return float(m.group(0).replace(",", ".")) if m else None


def _series(store, need, card, facts, as_of, outdated_days):
    pts = {}
    for f in facts:
        v = _value(f)
        if v is None or not f.get("date"):
            continue
        pts.setdefault((str(f["date"])[:10], v), []).append(f)
    if not pts:
        return not_documented(store, need, card)
    keys = sorted(pts)
    items = []
    for (d, v) in keys:
        it = group_items(store, pts[(d, v)])[0]
        items.append(it)
    collapse_series(items, lambda it: "series", keep_before_last=True)
    card["items"] = items
    card["collapsed"] = sum(1 for it in items if it.get("collapsed"))
    unit = (facts[0].get("attrs") or {}).get("unit") or ""
    parts = ["%g %s (%s)" % (v, unit, fmt_date(d)) for d, v in keys]
    card["value_en"] = " -> ".join(parts)
    card["date"] = keys[-1][0]
    card["status"] = "consistent"
    if len(keys) > 1:
        delta = keys[-1][1] - keys[0][1]
        months = round(((_d(keys[-1][0]) - _d(keys[0][0])).days) / 30.44)
        card["calculated"] = {"change": round(delta, 2), "unit": unit, "from": keys[0][0], "to": keys[-1][0],
                              "months": months, "method": "last minus first documented value"}
        card["value_en"] += "; change %+g %s over %d months (calculated)" % (delta, unit, months)
    if _older_than(card["date"], as_of, outdated_days):
        card["status"] = "outdated"
        card["note"] = "Last value from %s." % fmt_date(card["date"])
    return card


def _absent_after(store, need, card, facts, as_of, outdated_days):
    spec = need["compute"].split(":", 1)[1].strip()
    rec_items = []
    if re.match(r"^\d{4}-\d{2}-\d{2}$", spec):
        threshold = spec
    else:
        rx = re.compile(need.get("recommendation_match") or ".", re.I)
        recs = [f for f in store.facts if f.get("category") == "followup"
                and f.get("status") in ("recommended", "planned") and rx.search(fact_text(f))
                and str(f.get("date") or "") <= as_of]
        if not recs:
            card["value_en"] = "No such recommendation documented"
            return not_documented(store, need, card)
        threshold = max(str(f["date"])[:10] for f in recs)
        rec_items = group_items(store, recs)
        for it in rec_items:
            it["role"] = "recommendation"
    rec_ids = {fid for it in rec_items for fid in it["facts"]}
    done = [f for f in facts if f["id"] not in rec_ids and f.get("status") not in ("recommended", "planned")
            and _date_after(f, threshold)]
    card["threshold"] = threshold
    card["related"] = rec_items
    if done:
        items = group_items(store, done)
        items.sort(key=lambda it: str(it["date"] or ""), reverse=True)
        card["items"] = items
        card["value_en"] = "Documented after %s: %s" % (fmt_date(threshold), "; ".join(_with_date(it) for it in items[:5]))
        card["date"] = items[0]["date"]
        card["status"] = "consistent"
        return card
    rec_txt = ""
    if rec_items:
        rec_txt = " (recommended: %s)" % "; ".join(_with_date(it) for it in rec_items)
    not_documented(store, need, card)
    card["value_en"] = "No record that this took place after %s%s" % (fmt_date(threshold), rec_txt)
    return card


def _norm_sched(v):
    return re.sub(r"[\s-]+", "-", str(v or "").strip())


def _differs(old, cur):
    """True if an earlier mention states a different dose or schedule (not just less detail)."""
    a, b = old.get("attrs") or {}, cur.get("attrs") or {}
    for k in ("dose", "schedule", "frequency"):
        if a.get(k) and b.get(k) and _norm_sched(a[k]).lower() != _norm_sched(b[k]).lower():
            return True
    return False


def _current_meds(store, need, card, facts, as_of, outdated_days):
    med_dates = [str(f.get("date"))[:10] for f in store.facts
                 if f.get("ips_section") == "medications" and f.get("date") and str(f.get("date"))[:10] <= as_of]
    cur_dates = [str(f.get("date"))[:10] for f in store.facts
                 if f.get("ips_section") == "medications" and f.get("status") == "current"
                 and str(f.get("date") or "")[:10] <= as_of]
    list_date = max(cur_dates or med_dates or [""])
    card["list_date"] = list_date

    def drug(f):
        a = f.get("attrs") or {}
        return (a.get("generic") or (f.get("label_en") or "").split(" ")[0]).lower()

    current = [f for f in facts if str(f.get("date") or "")[:10] == list_date or f.get("status") == "current"]
    older = [f for f in facts if f not in current]
    has_dose = lambda f: any((f.get("attrs") or {}).get(k) for k in ("dose", "schedule", "amount", "frequency"))
    items = []
    for it in group_items(store, current):
        g = drug(store.fact_by_id[it["facts"][0]])
        same = [f for f in older if _key(f.get("label_en")) == _key(it["label_en"])]
        for f in same:  # earlier letters stating the identical drug/dose/schedule agree
            it["facts"].append(f["id"])
            for d in store.fact_docs(f):
                if d not in it["docs"]:
                    it["docs"].append(d)
            for p in f.get("passage_ids") or []:
                if p not in it["passages"]:
                    it["passages"].append(p)
            it["first_date"] = min(str(it["first_date"]), str(f.get("date")))
        cur_f = store.fact_by_id[it["facts"][0]]
        changed, agree = [], []
        for f in older:
            if drug(f) != g or f in same:
                continue
            (changed if _differs(f, cur_f) else agree).append(f)
        for f in agree:  # same drug, less detail (e.g. no schedule) but nothing contradicting
            it["facts"].append(f["id"])
            for d in store.fact_docs(f):
                if d not in it["docs"]:
                    it["docs"].append(d)
            for p in f.get("passage_ids") or []:
                if p not in it["passages"]:
                    it["passages"].append(p)
        if changed:
            it["earlier"] = [{"label_en": e["label_en"], "date": e["date"], "facts": e["facts"],
                              "passages": e["passages"]} for e in group_items(store, changed)]
        items.append(it)
    cur_drugs = {drug(store.fact_by_id[it["facts"][0]]) for it in items}
    stopped = [f for f in older if drug(f) not in cur_drugs and has_dose(f)]
    stopped_items = group_items(store, stopped)
    for it in stopped_items:
        it["not_on_latest_list"] = True
    card["date"] = list_date
    if items:
        card["items"] = items + stopped_items
        parts = []
        for it in items:
            s = it["label_en"]
            if it.get("earlier"):
                s += " [earlier: %s]" % "; ".join(_with_date(e) for e in it["earlier"])
            parts.append(s)
        if need.get("display") == "count":
            card["value_en"] = "%d drug(s) on the latest list (%s)" % (len(items), fmt_date(list_date))
        else:
            card["value_en"] = "; ".join(parts)
        if stopped_items:
            card["value_en"] += " | not on latest list (%s): %s" % (
                fmt_date(list_date), "; ".join(_with_date(it) for it in stopped_items))
        card["status"] = "consistent"
        return card
    if stopped_items:
        card["items"] = stopped_items
        card["value_en"] = "Not on the latest medication list (%s). Earlier: %s" % (
            fmt_date(list_date), "; ".join(_with_date(it) for it in stopped_items))
        card["status"] = "outdated"
        return card
    return not_documented(store, need, card, extra=" (none on any medication list; latest list %s)"
                          % fmt_date(list_date))


COMPUTE = {None: _list, "list": _list, "latest": _latest, "series_change": _series,
           "current_meds": _current_meds}


# ----------------------------------------------------------------- entry point

def fill(store, need, as_of, patient, contradictions=(), outdated_days=183):
    card = {"need": need.get("id"), "label_en": need.get("label_en"), "priority": need.get("priority", "should"),
            "compute": need.get("compute"), "status": None, "value_en": "", "date": None,
            "facts": [], "passages": [], "items": [], "source": need.get("source")}
    cond = need.get("applies_if") or {}
    for k, v in cond.items():
        pv = patient.get(k)
        if pv is not None and str(pv).lower() != str(v).lower():
            card["status"] = "not_applicable"
            card["value_en"] = "Not applicable: patient is %s" % pv
            card["passages"] = [p for p in [patient.get("%s_passage" % k)] if p]
            return card
    facts = select(store, need, as_of)
    comp = need.get("compute")
    fn = _absent_after if comp and comp.startswith("absent_after") else COMPUTE.get(comp, _list)
    fn(store, need, card, facts, as_of, outdated_days)
    return finish(store, card, contradictions, latest_only=(comp == "latest"))


def finish(store, card, contradictions=(), latest_only=False, primary_ids=None):
    """Collect the card's fact/passage ids and mark it conflicting if a counted contradiction touches it."""
    ids, pids = [], []
    for it in card.get("items") or []:
        for x in it["facts"]:
            if x not in ids:
                ids.append(x)
        for x in it["passages"]:
            if x not in pids:
                pids.append(x)
    card["facts"] = ids
    if ids:
        card["passages"] = pids
    primary = set(ids) if primary_ids is None else set(primary_ids)
    if latest_only and primary_ids is None and card.get("items"):
        # only the value being shown counts; an identical older value in another letter is support
        top = card["items"][0]
        primary = {x for x in top["facts"]
                   if str(store.fact_by_id[x].get("date") or "")[:10] == str(top["date"] or "")[:10]}
    touched = [c for c in contradictions if c.get("counted", True) and set(c["facts"]) & primary
               or (not c["facts"] and set(c["passages"]) & set(pids))]
    if touched and card["status"] in ("consistent", "outdated"):
        card["status_before_conflict"] = card["status"]
        card["status"] = "conflicting"
    if touched:
        card["conflicts"] = [c["id"] for c in touched]
    return card


# ================================================================= KB shapes
# The routing KB (rulebook/kb) gives every slot a display shape.  Each shape maps onto a compute type
# of this module; engine/kbfill.py selects the slot's facts (rulebook/slot_map.json) and calls these.
SHAPE_COMPUTE = {
    "current_list": "current_meds",        # _current_meds (class slots: filtered views of all medication)
    "latest_value": "latest_by_key",       # newest value per key + 'no later value documented' + R21
    "trend": "trend",                      # every dated value; change calculated for one numeric series
    "event_history": "list",               # dated list, newest first, with IBM status words
    "list_all": "list",
    "status_check": "status_check",        # recommendation -> evidence after it, else not documented
    "checklist": "checklist",              # sub-items: found / documented as none / not documented
    "plan": "plan",                        # planned or recommended items with date and who decided
    "laterality_finding": "laterality",    # finding with side; side summary (conflicts from compare/)
}

STATUS_DISPLAY = {  # KB status_vocabulary: IBM status -> on-screen word (positive = shown as a fact)
    "negative": "ruled out", "suspected": "suspected", "statuspost": "past",
    "recommended": "recommended", "planned": "planned",
}
STALE_MONTHS = 12  # KB rule R21


def months_between(a, b):
    da, db = _d(a), _d(b)
    if not da or not db:
        return None
    return (db.year - da.year) * 12 + (db.month - da.month)


def annotate_status(store, items):
    """Attach the KB status word (ruled out / suspected / past / planned ...) of each item's newest fact."""
    for it in items:
        fs = [store.fact_by_id[x] for x in it["facts"] if x in store.fact_by_id]
        if not fs:
            continue
        newest = [f for f in fs if str(f.get("date") or "")[:10] == str(it.get("date") or "")[:10]] or fs
        f = newest[-1]
        word = STATUS_DISPLAY.get((f.get("attrs") or {}).get("assertion")) or STATUS_DISPLAY.get(f.get("status"))
        if word:
            it["status_display"] = word
    return items


def shown(it):
    s = _with_date(it) if it.get("date") else it["label_en"]
    word = it.get("status_display")
    if word == "ruled out" and re.match(r"(no|not|without)\b", str(it["label_en"] or ""), re.I):
        word = None  # 'No complex ventricular arrhythmias' already says it
    if word and word.lower() in str(it["label_en"] or "").lower():
        word = None  # 'check-ups recommended' needs no '[recommended]'
    return s + (" [%s]" % word if word else "")


def _attr_key(f, key):
    if key.startswith("attrs."):
        return str((f.get("attrs") or {}).get(key[6:]) or f.get("category"))
    return str(f.get(key) or "")


def latest_by_key(store, card, facts, context, anchor, key="category"):
    """Newest value per key (category by default); older values go to card['earlier']."""
    groups = {}
    for f in facts:
        groups.setdefault(_attr_key(f, key), []).append(f)
    tops, earlier = [], []
    rank = lambda it: (str(it["date"] or ""), it["status"] == "current", max(it["docs"] or [""]))
    for k in sorted(groups, key=lambda k: min(x["id"] for x in groups[k])):
        items = annotate_status(store, group_items(store, groups[k]))
        items.sort(key=rank, reverse=True)
        tops.append(items[0])
        earlier += [{"label_en": it["label_en"], "date": it["date"], "facts": it["facts"],
                     "passages": it["passages"]} for it in items[1:4]]
    ctx_items = annotate_status(store, group_items(store, context))
    # an open question or suspicion ('Atrial fibrillation?', 'Question: arrhythmias') adds nothing beside the
    # findings that answered it; it stays only when the card has nothing else
    answered = [it for it in ctx_items if not _is_question(store, it)]
    if tops or answered:
        ctx_items = answered
    for it in ctx_items:
        it["context"] = True
    card["items"] = tops + ctx_items
    card["earlier"] = earlier
    card["value_en"] = "; ".join(shown(t) for t in tops)
    if ctx_items:
        card["value_en"] += " | related: " + "; ".join(shown(it) for it in ctx_items[:6])
    newest = max(str(t["date"] or "") for t in tops)
    card["date"] = newest
    card["status"] = "consistent"
    plan = all(t["status"] in ("planned", "recommended") for t in tops)
    age = months_between(newest, anchor)
    prec = max((t.get("date_precision") or "day" for t in tops if str(t["date"] or "") == newest), default="day")
    if not plan and age is not None and age > STALE_MONTHS:
        card["status"] = "outdated"
        card["note"] = "As of %s; nothing newer documented (older than %d months: rule R21)." % (
            fmt_date(newest, "month"), STALE_MONTHS)
        card["rules_applied"] = ["R21"]
    elif not plan and age is not None and age > 0:
        card["note"] = "As of %s; no later value documented." % fmt_date(newest, "month" if prec != "year" else prec)
    card["primary_ids"] = [x for t in tops for x in t["facts"]
                           if str(store.fact_by_id[x].get("date") or "")[:10] == str(t["date"] or "")[:10]]
    return card


def _is_question(store, it):
    lab = str(it.get("label_en") or "").strip()
    fs = [store.fact_by_id[x] for x in it.get("facts") or [] if x in store.fact_by_id]
    return lab.lower().startswith("question:") or lab.endswith("?") or \
        bool(fs) and all((f.get("attrs") or {}).get("assertion") == "suspected" for f in fs)


def trend(store, card, facts, calculate_change=True):
    """Every dated value; a change is calculated (last minus first) only for one numeric series."""
    cats = {f.get("category") for f in facts}
    numeric = all(_num_attr(f) is not None for f in facts)
    if calculate_change and len(cats) == 1 and numeric:
        return _series(store, {}, card, facts, "9999-12-31", 10 ** 6)
    items = annotate_status(store, group_items(store, facts))
    items.sort(key=lambda it: (str(it["date"] or ""), it["label_en"]))
    items = dedupe_readings(store, items)
    collapse_series(items, _measure_of)
    card["items"] = items
    card["collapsed"] = sum(1 for it in items if it.get("collapsed"))
    # '->' only for one measure over time; different measures (24h / day / night mean) are listed
    sep = " -> " if len({_measure_of(it) for it in items}) <= 1 and \
        len({str(it.get("date") or "")[:10] for it in items}) == len(items) else "; "
    card["value_en"] = sep.join(shown(it) for it in items[-12:])
    card["date"] = items[-1]["date"] if items else None
    card["status"] = "consistent"
    return card


_MEASURE = re.compile(r"^[^\d:(]*")


def _measure_of(it):
    """'Blood pressure 145/90 mmHg (after treatment)' -> 'blood pressure' (one series per measure)."""
    return _MEASURE.match(it.get("label_en") or "").group(0).strip().lower() or "value"


def _reading_value(store, it):
    fs = [store.fact_by_id[x] for x in it["facts"] if x in store.fact_by_id]
    vals = {str((f.get("attrs") or {}).get("value") or "") for f in fs} - {""}
    return min(vals) if len(vals) == 1 else None


def dedupe_readings(store, items):
    """Near-identical readings (same measure, same value, same day, only the context words differ, e.g.
    '145/90 mmHg (after treatment)' and '145/90 mmHg (on admission, after treatment)') -> one item; the
    other wording stays attached (also_as) with all its facts and passages, so no source link is lost."""
    out, seen = [], {}
    for it in items:
        v = _reading_value(store, it)
        k = (_measure_of(it), v, str(it.get("date") or "")[:10]) if v else None
        rep = seen.get(k) if k else None
        if rep is None:
            if k:
                seen[k] = it
            out.append(it)
            continue
        rep["facts"] = list(dict.fromkeys(rep["facts"] + it["facts"]))
        rep["passages"] = list(dict.fromkeys(rep["passages"] + it["passages"]))
        rep["docs"] = sorted(set(rep["docs"]) | set(it["docs"]))
        rep.setdefault("also_as", []).append(it["label_en"])
    return out


TREND_VISIBLE = 4  # a series with more readings shows first, the one before the latest, and the latest


def collapse_series(items, measure, keep_before_last=False):
    """Mark the middle readings of each measure 'collapsed' (still in the response, behind '+N more');
    the earliest and latest stay visible, so the change between them is always on screen."""
    by = {}
    for i, it in enumerate(items):
        by.setdefault(measure(it), []).append(i)
    for idx in by.values():
        if len(idx) <= (TREND_VISIBLE if keep_before_last else 2):
            continue
        keep = {idx[0], idx[-1]} | ({idx[-2]} if keep_before_last else set())
        for i in idx:
            if i not in keep:
                items[i]["collapsed"] = True
    return items


def _num_attr(f):
    try:
        return float(str((f.get("attrs") or {}).get("value")).replace(",", "."))
    except (TypeError, ValueError):
        return None


_Q_STOP = {"question", "suspected", "suspicion", "diagnosis", "of", "the", "with", "and", "in", "on", "left", "right"}


def _concept_words(label):
    t = re.sub(r"\(.*?\)", " ", str(label or "").lower())
    return {w for w in re.findall(r"[a-zäöüß]{3,}", t) if w not in _Q_STOP}


def drop_answered_questions(store, items):
    """An open question or suspicion ('Amaurosis fugax?', 'Question: hypertensive retinopathy') is left out
    when the same list has a confirmed finding that contains all its words ('Amaurosis fugax', 'Incipient
    hypertensive retinopathy'); questions nothing answered stay."""
    firm = [_concept_words(it["label_en"]) for it in items if not _is_question(store, it)]
    out = []
    for it in items:
        q = _concept_words(it["label_en"]) if _is_question(store, it) else None
        if q and any(q <= w for w in firm):
            continue
        out.append(it)
    return out


def dated_list(store, card, facts, newest_first=True, limit=12):
    items = drop_answered_questions(store, annotate_status(store, group_items(store, facts)))
    items.sort(key=lambda it: str(it["date"] or ""), reverse=newest_first)
    card["items"] = items
    more = len(items) - limit
    card["value_en"] = "; ".join(shown(it) for it in items[:limit]) + (" (+%d more)" % more if more > 0 else "")
    card["date"] = max((str(it["date"] or "") for it in items), default=None)
    card["status"] = "consistent"
    return card


_QUESTION = re.compile(r"\?\s*$|^\s*(question|fragestellung|frage)\b", re.I)
_CONCEPT_STRIP = re.compile(r"^(history of|known|status post|s/p|diagnosis:|suspected)\s+", re.I)


def _assertion(f):
    return (f.get("attrs") or {}).get("assertion")


def is_question(f):
    """A suspicion, not a finding: IBM 'suspected', or a label ending '?' / starting 'Question'."""
    return _assertion(f) == "suspected" or bool(_QUESTION.search(f.get("label_en") or ""))


def concept_key(f):
    """Same concept = same code (ICD-10 or other system), else the same normalised English label."""
    code = f.get("code") if isinstance(f.get("code"), dict) else None
    if code and code.get("value"):
        return "code:%s:%s" % (code.get("system") or "", str(code["value"]).upper())
    t = re.sub(r"\(.*?\)", " ", (f.get("label_en") or "").lower())
    t = _CONCEPT_STRIP.sub("", t.strip())
    return "label:" + " ".join(re.findall(r"[a-z0-9äöüß%]+", t))


def merge_items(store, facts, keyfn):
    """One item per concept: the newest statement is shown, the other mentions (other wording, other
    letters) stay attached as extra source links."""
    groups = {}
    for f in facts:
        groups.setdefault(keyfn(f), []).append(f)
    out = []
    for fs in groups.values():
        items = group_items(store, fs)
        items.sort(key=lambda it: (str(it["date"] or ""), it.get("status") == "current",
                                   -len(it.get("label_en") or "")), reverse=True)
        rep = dict(items[0])
        others = items[1:]
        if others:
            rep["facts"] = [x for o in others for x in o["facts"] if x not in rep["facts"]] + list(rep["facts"])
            rep["passages"] = list(dict.fromkeys(rep["passages"] + [x for o in others for x in o["passages"]]))
            rep["docs"] = sorted(set(rep["docs"]) | {x for o in others for x in o["docs"]})
            rep["first_date"] = min((str(o.get("first_date") or "") for o in items if o.get("first_date")),
                                    default=rep.get("first_date"))
            rep["also_as"] = [o["label_en"] for o in others if _key(o["label_en"]) != _key(rep["label_en"])]
        out.append(rep)
    return out


def allergen_key(f):
    a = f.get("attrs") or {}
    neg = _assertion(f) == "negative"
    sub = str(a.get("substance") or a.get("allergen") or "").strip().lower()
    return ("neg:" if neg else "") + (sub or concept_key(f))


LIST_LIMIT_SHORT = 8


def list_all(store, card, facts, context=(), detail="short", keep_ruled_out=False, limit=LIST_LIMIT_SHORT):
    """Deduplicated list: one item per concept (code or label, newest wins), no ruled-out findings
    (unless the slot asks for them) and no open questions ('X?'); active items first, newest first.
    Short mode shows at most `limit` items and says how many more exist."""
    excluded = {"ruled_out": 0, "suspected": 0}
    keep = []
    for f in facts:
        if _assertion(f) == "negative" and not keep_ruled_out:
            excluded["ruled_out"] += 1
        elif is_question(f):
            excluded["suspected"] += 1
        else:
            keep.append(f)
    items = annotate_status(store, merge_items(store, keep, concept_key))

    def active(it):
        return it.get("status") in ("current", "active") and it.get("status_display") not in ("past", "ruled out")
    items.sort(key=lambda it: str(it["date"] or ""), reverse=True)
    items.sort(key=lambda it: not active(it))
    if detail != "short" and context:
        ids = {x for it in items for x in it["facts"]}
        ctx = [f for f in context if f["id"] not in ids and _assertion(f) != "negative" and not is_question(f)]
        for it in annotate_status(store, merge_items(store, ctx, concept_key)):
            it["context"] = True
            items.append(it)
    total = len(items)
    shown_items = items[:limit] if detail == "short" else items
    card["items"] = shown_items
    card["hidden_items"] = items[len(shown_items):]  # kept (collapsed) by kbfill, never dropped silently
    card["more"] = total - len(shown_items)
    card["excluded"] = excluded
    card["value_en"] = "; ".join(shown(it) for it in shown_items) + (
        " (+%d more)" % card["more"] if card["more"] else "")
    card["date"] = max((str(it["date"] or "") for it in shown_items), default=None)
    card["status"] = "consistent" if shown_items else "not_documented"
    hidden = [("%d ruled out" % excluded["ruled_out"]) if excluded["ruled_out"] else "",
              ("%d open question(s)/suspicion(s)" % excluded["suspected"]) if excluded["suspected"] else ""]
    hidden = [h for h in hidden if h]
    if hidden:
        card["note"] = "Not listed: %s (see the source documents)." % ", ".join(hidden)
    return card


def plan(store, card, facts):
    dated_list(store, card, facts)
    for it in card["items"]:
        for x in it["facts"]:
            who = (store.fact_by_id[x].get("attrs") or {}).get("decided_by")
            if who:
                it["decided_by"] = who
    card["value_en"] = "; ".join(shown(it) + (" - decided by %s" % it["decided_by"] if it.get("decided_by") else "")
                                 for it in card["items"][:8])
    return card


_SIDE = re.compile(r"\b(left|right|bilateral|both sides)\b", re.I)


def laterality(store, card, facts):
    dated_list(store, card, facts)
    sides = {}
    for it in card["items"]:
        found = set()
        for x in it["facts"]:
            f = store.fact_by_id[x]
            s = str((f.get("attrs") or {}).get("side") or "").lower()
            found |= {s} if s in ("left", "right", "both") else {m.lower() for m in _SIDE.findall(f.get("label_en") or "")}
        found = {"both" if s in ("bilateral", "both sides") else s for s in found}
        if found:
            it["side"] = "/".join(sorted(found))
            for s in found:
                sides[s] = sides.get(s, 0) + 1
    card["sides"] = sides
    if sides:
        # headline: the finding on the side most statements give (the most specific wording: a degree in %
        # or a number first), then the other side(s) by their own finding; the statement counts stay in
        # card['sides'] and the full list in the items
        ranked = sorted(sides.items(), key=lambda kv: -kv[1])

        def best(side):
            its = [it for it in card["items"] if side in str(it.get("side") or "").split("/")]
            its.sort(key=lambda it: (not re.search(r"\d", it["label_en"] or ""), it.get("collapsed", False)))
            return its[0] if its else None
        main_side, _ = ranked[0]
        head = [best(main_side)]
        head += [best(s) for s, _ in ranked[1:] if best(s) is not None and best(s) is not head[0]]
        lead = "%s: %s" % (main_side.capitalize(), shown(head[0]))
        # a minority side is not presented as a second finding: it says how few statements give it (often the
        # side-swap that 'Letters disagree' flags)
        total = sum(sides.values())
        others = ["%s in %d of %d statements: %s" % (s, n, total, shown(best(s))) for s, n in ranked[1:]
                  if best(s) is not None]
        rest = [shown(it) for it in card["items"] if all(it is not h for h in head)][:6]
        card["value_en"] = "; ".join([lead] + others) + (
            " | " + "; ".join(rest) if rest else "")
    return card


def checklist(store, card, facts, subitems, none_match=None):
    """Each sub-item independently: found (facts linked) / documented as none / not documented."""
    none_rx = re.compile(none_match, re.I) if none_match else None
    negatives = [f for f in facts if none_rx and none_rx.search(fact_text(f))
                 or (f.get("attrs") or {}).get("assertion") == "negative"]
    positives = [f for f in facts if f not in negatives]
    items = annotate_status(store, merge_items(store, facts, allergen_key))
    items.sort(key=lambda it: str(it["date"] or ""), reverse=True)
    card["items"] = items
    rows, used = [], set()
    for sub in subitems:
        r = re.compile(sub["match"], re.I)
        hit = [f for f in positives if r.search(fact_text(f))]
        neg = [f for f in negatives if r.search(fact_text(f))] or ([f for f in negatives if none_rx and none_rx.search(fact_text(f))])
        used |= {f["id"] for f in hit}
        if hit:
            row = {"label": sub["label"], "status": "found", "facts": [f["id"] for f in hit],
                   "passages": sorted({p for f in hit for p in f.get("passage_ids") or []})}
        elif neg:
            row = {"label": sub["label"], "status": "documented_none", "facts": [f["id"] for f in neg],
                   "passages": sorted({p for f in neg for p in f.get("passage_ids") or []})}
        else:
            row = {"label": sub["label"], "status": "not_documented", "facts": [], "passages": []}
        rows.append(row)
    other = [f for f in positives if f["id"] not in used]
    if other:
        rows.append({"label": "Other", "status": "found", "facts": [f["id"] for f in other],
                     "passages": sorted({p for f in other for p in f.get("passage_ids") or []})})
    card["checklist"] = rows
    # one readable sentence: what was found, then what is documented as none / not documented (sub-item labels
    # in lower case, 'found' rows are already named by their findings)
    found_txt = "; ".join(it["label_en"] for it in items if not set(it["facts"]) & {f["id"] for f in negatives})
    by = lambda st_: ", ".join(r["label"][:1].lower() + r["label"][1:] for r in rows  # noqa: E731
                               if r["status"] == st_ and r["label"] != "Other")
    parts = [found_txt] if found_txt else []
    if by("documented_none"):
        parts.append("documented as none: " + by("documented_none"))
    if by("not_documented"):
        parts.append("not documented: " + by("not_documented"))
    card["value_en"] = ". ".join(p[:1].upper() + p[1:] for p in parts)
    card["date"] = items[0]["date"] if items else None
    card["status"] = "consistent" if items else "not_documented"
    return card


def status_check(store, card, recs, checks, evidence_fn, as_of):
    """For each recommendation: evidence of a matching kind dated after it, else 'not documented'."""
    rec_items = annotate_status(store, group_items(store, recs))
    rows, found_items = [], []
    for it in rec_items:
        it["role"] = "recommendation"
        text = " ".join(fact_text(store.fact_by_id[x]) for x in it["facts"])
        chk = next((c for c in checks if re.search(c["recommendation_match"], text, re.I)), None)
        threshold = str(it["date"] or "")[:10]
        row = {"label": it["label_en"], "check": chk["label"] if chk else None, "threshold": threshold,
               "recommendation": it}
        if chk is None:
            row.update(status="not_documented", facts=[], passages=[],
                       note="no evidence search defined for this kind of follow-up")
        else:
            ev = [f for f in evidence_fn(chk["evidence"]) if f["id"] not in it["facts"]
                  and f.get("status") not in ("recommended", "planned") and _date_after(f, threshold)
                  and str(f.get("date") or "")[:10] <= as_of]
            if ev:
                ev_items = annotate_status(store, group_items(store, ev))
                ev_items.sort(key=lambda x: str(x["date"] or ""), reverse=True)
                found_items += ev_items
                row.update(status="found", facts=[x for e in ev_items for x in e["facts"]],
                           passages=[x for e in ev_items for x in e["passages"]],
                           note="documented after %s: %s" % (fmt_date(threshold), "; ".join(shown(e) for e in ev_items[:3])))
            else:
                row.update(status="not_documented", facts=[], passages=[],
                           note="no record that this took place after %s" % fmt_date(threshold))
        rows.append(row)
    card["checklist"] = [{"label": r["label"], "status": r["status"], "facts": r["facts"],
                          "passages": r["passages"] or r["recommendation"]["passages"], "note": r["note"]}
                         for r in rows]
    card["related"] = rec_items
    card["open_checks"] = [{"label": r["label"], "threshold": r["threshold"], "note": r["note"],
                            "passages": r["recommendation"]["passages"]} for r in rows if r["status"] != "found"]
    card["threshold"] = min((r["threshold"] for r in rows), default=None)
    card["items"] = found_items
    card["value_en"] = " | ".join("%s: %s" % (r["label"], r["note"]) for r in rows)
    card["status"] = "consistent" if found_items else "not_documented"
    card["date"] = found_items[0]["date"] if found_items else None
    return card


def _dob(value):
    m = re.match(r"^\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s*$", str(value or ""))
    if m:
        return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return _d(value)


def age_years(dob, at):
    return at.year - dob.year - ((at.month, at.day) < (dob.month, dob.day))


def age_sex(store, card, facts, anchor, patient):
    """Age calculated from the date of birth at the anchor date (KB slot_notes: never the header age)."""
    sex = patient.get("sex")
    sex_p = [p for p in [patient.get("sex_passage")] if p]
    dob_f = next((f for f in facts if _dob((f.get("attrs") or {}).get("value"))), None)
    at = _d(anchor)
    if not dob_f or not at:
        card["status"] = "not_documented"
        card["value_en"] = "Date of birth not documented" + ("; sex: %s" % sex if sex else "")
        card["passages"] = sex_p
        return card
    dob = _dob(dob_f["attrs"]["value"])
    age = age_years(dob, at)
    items = group_items(store, [dob_f])
    card["items"] = items
    card["calculated"] = {"kind": "age", "age": age, "dob": dob.isoformat(), "at": anchor,
                          "method": "full years from the date of birth to the anchor date (latest document)"}
    card["value_en"] = "%d years (calculated from the date of birth %s at %s)%s" % (
        age, dob.strftime("%d.%m.%Y"), fmt_date(anchor), "; %s" % sex if sex else "")
    if sex_p:
        items[0]["passages"] = items[0]["passages"] + [p for p in sex_p if p not in items[0]["passages"]]
    card["status"] = "consistent"
    card["date"] = anchor
    checks = []  # KB check X02: stated age vs date of birth at the document date
    for f in store.facts:
        if f.get("category") != "age":
            continue
        stated = _num_attr(f)
        d = _d(f.get("date"))
        if stated is None or not d:
            continue
        calc = age_years(dob, d)
        checks.append({"id": "X02", "stated": stated, "calculated": calc, "date": f.get("date"), "fact": f["id"],
                       "agrees": abs(stated - calc) < 1})
    if checks:
        card["checks"] = checks
        bad = [c for c in checks if not c["agrees"]]
        card["note"] = ("Stated age differs from the date of birth: " + "; ".join(
            "%g stated vs %d calculated (%s)" % (c["stated"], c["calculated"], fmt_date(c["date"])) for c in bad)
            if bad else "Stated age in the letters agrees with the date of birth (check X02).")
    return card


def med_changes(store, card, facts, as_of):
    """Drugs no longer on the latest list, and the same drug with a different dose/schedule earlier."""
    tmp = {"status": None, "items": []}
    _current_meds(store, {}, tmp, facts, as_of, 0)
    items = []
    for it in tmp.get("items") or []:
        if it.get("not_on_latest_list"):
            items.append(dict(it, change="not on the latest list"))
        elif it.get("earlier"):
            for e in it["earlier"]:
                items.append(dict(e, docs=[], change="changed: now %s" % it["label_en"]))
            items.append(dict(it, change="current"))
    card["list_date"] = tmp.get("list_date")
    card["date"] = tmp.get("list_date")
    if not items:
        card["status"] = "not_documented"
        card["value_en"] = "No stopped or changed drug found between the medication lists (latest list %s)" % (
            fmt_date(tmp.get("list_date")))
        return card
    for it in items:
        it.setdefault("docs", [])
    card["items"] = items
    card["value_en"] = "; ".join("%s (%s): %s" % (it["label_en"], fmt_date(it["date"]), it["change"])
                                 for it in items)
    card["status"] = "consistent"
    return card
