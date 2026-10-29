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
    card["items"] = items
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
    primary = set(ids)
    if comp == "latest" and card.get("items"):
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
