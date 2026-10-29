"""Show: situation text -> one JSON screen.

{understood, safety_strip, cards, blind_spot, contradictions, proof_bar, timing_ms}
"""
import re
import time

from .conflicts import contradictions as find_contradictions
from .data import rulebook, store
from .fill import fill, fmt_date, group_items
from .understand import understand

_CONTRA_CACHE = {}


def _contradictions(st):
    key = id(st)
    if key not in _CONTRA_CACHE:
        _CONTRA_CACHE[key] = find_contradictions(st)
    return _CONTRA_CACHE[key]


def collect_needs(u, roles_rb, tasks_rb):
    role = next((r for r in roles_rb.get("roles", []) if r["id"] == u["role_id"]), {})
    task_by_id = {t["id"]: t for t in tasks_rb.get("tasks", [])}
    rows, seen = [], {}
    for tid in u["task_ids"]:
        for n in task_by_id.get(tid, {}).get("needs", []):
            n = dict(n, task=tid)
            if n["id"] in seen:
                prev = seen[n["id"]]
                if n.get("priority") == "must":
                    prev["priority"] = "must"
                continue
            seen[n["id"]] = n
            rows.append(n)
    for n in role.get("needs") or []:
        if n["id"] not in seen:
            seen[n["id"]] = dict(n, task="role")
            rows.append(seen[n["id"]])
    return [n for n in rows if n.get("priority") == "must"] + [n for n in rows if n.get("priority") != "must"]


_PROBLEM_STRIP = re.compile(r"^(history of|known|suspected|question:)\s+", re.I)


def _problem_key(label):
    t = _PROBLEM_STRIP.sub("", (label or "").lower()).strip()
    words = re.findall(r"[a-z0-9-]+", t)
    return " ".join(words[:2])


def blind_spot(st):
    """Problems on earlier diagnosis lists that the latest letter's diagnosis list no longer mentions."""
    lists = {}
    for f in st.facts:
        a = f.get("attrs") or {}
        if f.get("ips_section") not in ("problems", "past_illness"):
            continue
        if a.get("context") != "diagnosis list" and a.get("source") != "diagnosis":
            continue
        for d in st.fact_docs(f):
            lists.setdefault(d, []).append(f)
    if not lists:
        return None
    latest = max(lists, key=lambda d: (st.doc_date(d) or "", d))
    latest_keys = {_problem_key(f.get("label_en")) for f in lists[latest]}
    dropped = {}
    for d, fs in lists.items():
        if d == latest:
            continue
        for f in fs:
            k = _problem_key(f.get("label_en"))
            if k and k not in latest_keys:
                dropped.setdefault(k, []).append(f)
    items = []
    for k, fs in dropped.items():
        it = group_items(st, fs)
        it.sort(key=lambda x: str(x["date"] or ""), reverse=True)
        top = it[0]
        items.append({"label_en": top["label_en"], "last_documented": top["date"],
                      "facts": [x for i in it for x in i["facts"]],
                      "passages": [x for i in it for x in i["passages"]],
                      "docs": sorted({x for i in it for x in i["docs"]})})
    items.sort(key=lambda x: x["label_en"])
    total = len(latest_keys | set(dropped))
    return {"latest_document": latest, "latest_document_date": st.doc_date(latest),
            "missed_if_only_latest": len(items), "of_total_problems": total,
            "summary_en": "If you only read the latest letter (%s), you would miss %d of %d documented problems."
                          % (fmt_date(st.doc_date(latest)), len(items), total),
            "items": items}


def compare_blind_spot(st):
    """Blind spots computed by compare/ (preferred when data/build/compare.json exists)."""
    c = st.compare if isinstance(st.compare, dict) else None
    if not c or not c.get("blind_spots"):
        return None
    n = c.get("counts") or {}
    items = [{"label_en": b.get("label_en"), "kind": b.get("kind"), "last_documented": b.get("last_seen_date"),
              "facts": b.get("fact_ids") or [], "passages": b.get("passage_ids") or [],
              "docs": sorted({x.split(":")[0] for x in b.get("passage_ids") or []})}
             for b in c["blind_spots"]]
    missed = n.get("missed_if_only_latest_read", len(items))
    total = n.get("important_concepts")
    return {"latest_document": n.get("latest_doc"), "latest_document_date": n.get("latest_date"),
            "missed_if_only_latest": missed, "of_total_problems": total,
            "summary_en": "If you only read the latest letter (%s), you would miss %s of %s important facts."
                          % (fmt_date(n.get("latest_date")), missed, total),
            "items": items, "origin": "compare.json"}


def _annotate_followups(st, cards):
    c = st.compare if isinstance(st.compare, dict) else None
    if not c:
        return
    res = [(set(fu.get("fact_ids") or []), fu) for fu in c.get("open_followups") or []]
    for card in cards:
        for it in card.get("items") or []:
            for ids, fu in res:
                if ids & set(it["facts"]):
                    it["followup_resolution"] = fu.get("resolution")
                    it["followup_open"] = fu.get("is_open")


def build_screen(text, as_of=None, use_llm=True):
    t0 = time.perf_counter()
    st = store()
    roles_rb, tasks_rb = rulebook()
    u = understand(text, as_of=as_of, use_llm=use_llm)
    as_of = u["as_of_date"]
    sex, sex_pid = st.patient_sex()
    patient = {"sex": sex, "sex_passage": sex_pid}
    contras, csource = _contradictions(st)
    days = roles_rb.get("outdated_after_days", 183)

    safety = [fill(st, n, as_of, patient, contras, days) for n in roles_rb.get("safety_strip", [])]
    bs = compare_blind_spot(st) or blind_spot(st)
    for c in safety:
        if c["need"] == "problems" and bs:
            c["not_in_latest_letter"] = [i["label_en"] for i in bs["items"]]
    cards = [fill(st, n, as_of, patient, contras, days) for n in collect_needs(u, roles_rb, tasks_rb)]
    for c, n in zip(cards, collect_needs(u, roles_rb, tasks_rb)):
        c["task"] = n.get("task")
    _annotate_followups(st, cards)

    shown = []
    for c in safety + cards:
        for x in c["facts"]:
            if x not in shown:
                shown.append(x)
    shown_set = set(shown)
    contra_out = [dict(c, relevant=bool(set(c["facts"]) & shown_set)) for c in contras]
    contra_out.sort(key=lambda c: not c["relevant"])
    verified = [x for x in shown if st.fact_by_id.get(x, {}).get("verified") is not False]
    counts = {}
    for c in cards:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    return {
        "understood": u,
        "patient": {"sex": sex, "sex_passage": sex_pid},
        "safety_strip": safety,
        "cards": cards,
        "card_status_counts": counts,
        "blind_spot": bs,
        "contradictions": contra_out,
        "contradictions_source": csource,
        "proof_bar": {"facts_shown": len(shown), "facts_verified": len(verified),
                      "facts_removed_at_load": len(st.removed),
                      "summary_en": "%d facts shown - %d checked word for word against the letters - %d removed"
                                    % (len(shown), len(verified), len(st.removed))},
        "timing_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
