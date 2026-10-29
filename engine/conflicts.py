"""Contradictions for the screen.

Primary source: data/build/compare.json (built by compare/).  The reader is
tolerant of its exact layout: it accepts a list or {"contradictions": [...]}
and collects fact ids (f0001) and passage ids (<doc>:p0001) found anywhere in
an entry.  Entries marked counted=false / false_alarm / suppressed are skipped.

Fallback (only if compare.json is absent): three conservative checks
  * same finding with the same value written for opposite body sides
  * BMI that does not match height and weight stated in the same document
  * two different admission dates for the same stay in the same document
"""
import re

_FACT_RX = re.compile(r"^f\d+$")
_PASS_RX = re.compile(r"^\d+:p\d+$")


def _collect_ids(obj, facts, passages):
    if isinstance(obj, str):
        if _FACT_RX.match(obj):
            facts.add(obj)
        elif _PASS_RX.match(obj):
            passages.add(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_ids(v, facts, passages)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect_ids(v, facts, passages)


def _counted(entry):
    if entry.get("tier") not in (None, "counted"):
        return False
    if entry.get("counted") is False or entry.get("false_alarm") or entry.get("suppressed"):
        return False
    return str(entry.get("status", "")).lower() not in ("suppressed", "false_alarm", "rejected", "ignored")


def from_compare(compare, store):
    entries = compare.get("contradictions", compare.get("items", [])) if isinstance(compare, dict) else compare
    chains = {}
    if isinstance(compare, dict):
        for pr in compare.get("propagation") or []:
            for cid in pr.get("contradiction_ids") or []:
                chains.setdefault(cid, []).append(pr)
    out = []
    for i, e in enumerate(entries or []):
        if not isinstance(e, dict):
            continue
        facts, passages = set(), set()
        _collect_ids(e, facts, passages)
        for fid in facts:
            f = store.fact_by_id.get(fid)
            if f:
                passages |= set(f.get("passage_ids") or [])
        out.append({
            "id": str(e.get("id") or "c%02d" % (i + 1)),
            "title_en": (e.get("title_en") or e.get("summary_en") or e.get("title") or e.get("summary")
                         or e.get("name") or "Contradiction"),
            "detail_en": e.get("detail_en") or e.get("rationale") or e.get("explanation") or e.get("detail") or "",
            "kind": e.get("kind"),
            "counted": _counted(e),
            "claims": e.get("claims") or [],
            "propagation": chains.get(str(e.get("id")), []),
            "facts": sorted(facts),
            "passages": sorted(passages),
            "origin": "compare.json",
        })
    return out


def _num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _mk(cid, title, detail, facts):
    passages = sorted({p for f in facts for p in (f.get("passage_ids") or [])})
    return {"id": cid, "title_en": title, "detail_en": detail, "facts": sorted(f["id"] for f in facts),
            "passages": passages, "origin": "engine-fallback", "counted": True}


def fallback(store):
    out = []
    facts = store.facts
    # 1. same category + same value, opposite sides
    groups = {}
    for f in facts:
        a = f.get("attrs") or {}
        side = str(a.get("side") or "").lower()
        if side in ("left", "right") and a.get("value") not in (None, ""):
            groups.setdefault((f.get("category"), str(a.get("value")), a.get("unit")), {}).setdefault(side, []).append(f)
    for (cat, val, unit), sides in sorted(groups.items(), key=lambda kv: str(kv[0])):
        if len(sides) == 2:
            fs = sides["left"] + sides["right"]
            out.append(_mk("fb-side-%s" % cat, "%s %s%s: left in %d fact(s), right in %d"
                           % (cat.replace("_", " ").capitalize(), val, unit or "", len(sides["left"]), len(sides["right"])),
                           "Same finding and value written for opposite sides.", fs))
    # 2. BMI vs height/weight in the same document
    per_doc = {}
    for f in facts:
        if f.get("category") in ("height", "weight", "bmi"):
            for d in store.fact_docs(f):
                per_doc.setdefault(d, {}).setdefault(f["category"], f)
    for d, m in sorted(per_doc.items()):
        if len(m) == 3:
            h, w, b = (_num((m[k].get("attrs") or {}).get("value")) for k in ("height", "weight", "bmi"))
            if h and w and b:
                hm = h / 100.0 if h > 3 else h
                calc = w / (hm * hm)
                if abs(calc - b) > 1.0:
                    out.append(_mk("fb-bmi-%s" % d, "BMI %s written, but %s kg / %s cm gives %.1f (document %s)"
                                   % ((m["bmi"]["attrs"] or {}).get("value"), (m["weight"]["attrs"] or {}).get("value"),
                                      (m["height"]["attrs"] or {}).get("value"), calc, d),
                                   "Calculated BMI = weight / height²; difference > 1 kg/m².",
                                   [m["height"], m["weight"], m["bmi"]]))
    # 3. two admission dates for one stay in the same document
    adm = {}
    for f in facts:
        if f.get("category") != "encounter":
            continue
        a = f.get("attrs") or {}
        txt = a.get("admission") or (a.get("date_text") if a.get("event") == "admission" else None)
        m = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", str(txt or ""))
        if m:
            iso = "%s-%02d-%02d" % (m.group(3), int(m.group(2)), int(m.group(1)))
            for d in store.fact_docs(f):
                adm.setdefault(d, {}).setdefault(iso, []).append(f)
    for d, dates in sorted(adm.items()):
        if len(dates) > 1:
            fs = [f for v in dates.values() for f in v]
            out.append(_mk("fb-admission-%s" % d, "Two admission dates in document %s: %s"
                           % (d, " vs ".join(sorted(dates))), "Same stay, different admission dates.", fs))
    return out


def contradictions(store):
    if store.compare is not None:
        return from_compare(store.compare, store), "compare.json"
    return fallback(store), "engine-fallback"
