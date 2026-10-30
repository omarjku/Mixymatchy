"""Statistics worth displaying (organisers' sheet 'statistics-worth-displaying', docs/DECISIONS.md 23).

Arithmetic on verified facts only, each result a computed line that links every input passage:

  daily_dose_change  the prescribed daily total of one drug on the earliest and the latest list
                     (16 mg 1-0-1/2 = 24 mg/day -> 16 mg 1-0-1 = 32 mg/day: +8 mg/day, +33%); the prescribed
                     schedule, not adherence or dose appropriateness
  bmi_check          per letter, the recorded BMI against weight / height^2 from the same letter; a difference
                     above 0.5 kg/m^2 (data-quality tolerance, not a clinical threshold) is 'inconsistent'; the
                     recorded value is never replaced
  bp_day_night       daytime against night-time mean of one 24-h report; never pooled with spot readings

HbA1c, ejection fraction and height stay dated facts: no trend or change is computed for them.
"""
import re

from .fill import fmt_date

TOLERANCE_BMI = 0.5

_NUM = r"(\d+(?:[.,]\d+)?|\d+/\d+|½|¼|¾)"
_DOSE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(mg|g|µg|ug|mcg|ie|i\.e\.|iu)\b", re.I)
_FRACTIONS = {"½": 0.5, "¼": 0.25, "¾": 0.75}


def _num(tok):
    tok = tok.strip()
    if tok in _FRACTIONS:
        return _FRACTIONS[tok]
    if re.fullmatch(r"\d+/\d+", tok):
        a, b = tok.split("/")
        return int(a) / int(b) if int(b) else None
    if re.fullmatch(r"\d+(?:[.,]\d+)?", tok):
        return float(tok.replace(",", "."))
    return None


def schedule_total(schedule):
    """German dosing scheme ('1-0-1/2', '1 0 1/2 0', '0-1-0', '1-1-1') -> units per day, or None."""
    s = str(schedule or "").strip()
    if not s:
        return None
    toks = re.split(r"\s*-\s*|\s+", s)
    if not 3 <= len(toks) <= 4:
        return None
    vals = [_num(t) for t in toks]
    if any(v is None for v in vals):
        return None
    return sum(vals)


def _fmt(x):
    return ("%.2f" % x).rstrip("0").rstrip(".")


def daily_total(f):
    """-> (amount per day, unit, dose amount, schedule text) from a medication fact, or None."""
    a = f.get("attrs") or {}
    m = _DOSE.match(str(a.get("dose") or ""))
    sched = a.get("schedule") or a.get("schedule_mo_mi_ab_na")
    per_day = schedule_total(sched)
    if not m or per_day is None:
        return None
    amount = float(m.group(1).replace(",", "."))
    unit = {"ug": "µg", "mcg": "µg", "i.e.": "IU", "ie": "IU", "iu": "IU"}.get(m.group(2).lower(), m.group(2).lower())
    return amount * per_day, unit, amount, str(a.get("schedule") or sched)


def _when(store, f):
    docs = sorted(str(store.doc_date(d) or "")[:10] for d in store.fact_docs(f))
    return str(f.get("date") or "")[:10] or (docs[-1] if docs else ""), docs[-1] if docs else ""


def daily_dose_change(store, facts):
    """One line per drug whose prescribed daily total differs between its earliest and latest list."""
    by_drug = {}
    for f in facts:
        if f.get("ips_section") != "medications":
            continue
        t = daily_total(f)
        if t is None:
            continue
        name = str((f.get("attrs") or {}).get("generic") or re.split(r"\s*\(", f.get("label_en") or "")[0]).strip()
        if name:
            by_drug.setdefault(name.lower(), (name, []))[1].append((_when(store, f), f, t))
    lines = []
    for _key, (name, rows) in by_drug.items():
        rows.sort(key=lambda r: r[0])
        (w0, f0, t0), (w1, f1, t1) = rows[0], rows[-1]
        if f0 is f1 or t0[1] != t1[1] or abs(t0[0] - t1[0]) < 1e-9 or w0[0] == w1[0]:
            continue
        unit = t0[1]
        change = t1[0] - t0[0]
        pct = (" (%+.0f%%)" % (100 * change / t0[0])) if t0[0] else ""
        lines.append({
            "stat": "daily_dose_change", "key": True,
            "label": "%s%s daily dose" % (name[:1].upper(), name[1:]),
            "value": "%s → %s %s/day: %+g %s/day%s" % (_fmt(t0[0]), _fmt(t1[0]), unit, round(change, 2), unit, pct),
            "formula": "%s %s × (%s) = %s %s/day (%s); %s %s × (%s) = %s %s/day (%s); prescribed schedule, not "
                       "adherence or dose appropriateness" % (
                           _fmt(t0[2]), unit, t0[3], _fmt(t0[0]), unit, fmt_date(w0[0]),
                           _fmt(t1[2]), unit, t1[3], _fmt(t1[0]), unit, fmt_date(w1[0])),
            "passages": list(dict.fromkeys((f0.get("passage_ids") or []) + (f1.get("passage_ids") or [])))})
    return lines


def _value(f):
    try:
        return float(str((f.get("attrs") or {}).get("value") or "").replace(",", "."))
    except ValueError:
        return None


def _in_time(store, f, as_of):
    if not as_of:
        return True
    d = str(f.get("date") or "")[:10]
    docs = [str(store.doc_date(x) or "")[:10] for x in store.fact_docs(f)]
    return (not d or d <= str(as_of)[:10]) and any(x and x <= str(as_of)[:10] for x in docs)


def bmi_check(store, as_of=None):
    """Per letter with exactly one height, weight and stated BMI: recorded against calculated BMI."""
    per_doc = {}
    for f in store.facts:
        if f.get("category") in ("height", "weight", "bmi") and _in_time(store, f, as_of):
            docs = store.fact_docs(f)
            if len(docs) == 1:
                per_doc.setdefault(docs[0], {}).setdefault(f["category"], []).append(f)
    lines = []
    for doc, got in per_doc.items():
        if any(len(got.get(c) or []) != 1 for c in ("height", "weight", "bmi")):
            continue
        h, w, b = got["height"][0], got["weight"][0], got["bmi"][0]
        hv, wv, bv = _value(h), _value(w), _value(b)
        if not hv or not wv or bv is None:
            continue
        calc = wv / (hv / 100) ** 2
        diff = bv - calc
        verdict = "agrees within %g" % TOLERANCE_BMI if abs(diff) <= TOLERANCE_BMI else "inconsistent"
        lines.append({
            "stat": "bmi_check", "doc": doc, "date": str(store.doc_date(doc) or "")[:10],
            "consistent": abs(diff) <= TOLERANCE_BMI,
            "label": "BMI, letter of %s" % fmt_date(store.doc_date(doc)),
            "value": "recorded %s, calculated %.2f from %s kg and %s cm: %+.2f, %s" % (
                _fmt(bv), calc, _fmt(wv), _fmt(hv), diff, verdict),
            "formula": "weight / height² = %s / %.2f² = %.2f kg/m²; recorded minus calculated; tolerance %g kg/m² "
                       "is a data-quality tolerance, not a clinical threshold; the recorded value is kept"
                       % (_fmt(wv), hv / 100, calc, TOLERANCE_BMI),
            "passages": list(dict.fromkeys((h.get("passage_ids") or []) + (w.get("passage_ids") or [])
                                           + (b.get("passage_ids") or [])))})
    lines.sort(key=lambda x: x["date"])
    if lines:  # the newest letter's check goes into the key facts
        lines[-1]["key"] = True
    return lines


_DAY = re.compile(r"\bday(?:time)?\s+mean\b|tagesmittel", re.I)
_NIGHT = re.compile(r"\bnight(?:-?time)?\s+mean\b|nachtmittel", re.I)


def _bp(f):
    m = re.fullmatch(r"\s*(\d{2,3})\s*/\s*(\d{2,3})\s*", str((f.get("attrs") or {}).get("value") or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def bp_day_night(store, as_of=None):
    """Daytime against night-time mean of the same 24-h report (one line per report)."""
    per_doc = {}
    for f in store.facts:
        if f.get("category") != "blood_pressure" or not _in_time(store, f, as_of) or _bp(f) is None:
            continue
        ctx = str((f.get("attrs") or {}).get("context") or "")
        kind = "day" if _DAY.search(ctx) else "night" if _NIGHT.search(ctx) else None
        if kind:
            for d in store.fact_docs(f):
                per_doc.setdefault(d, {}).setdefault(kind, []).append(f)
    lines = []
    for doc, got in per_doc.items():
        if len(got.get("day") or []) != 1 or len(got.get("night") or []) != 1:
            continue
        day, night = got["day"][0], got["night"][0]
        (ds, dd), (ns, nd) = _bp(day), _bp(night)
        lines.append({
            "stat": "bp_day_night", "key": True,
            "label": "Blood pressure day vs night, 24-h report of %s" % fmt_date(store.doc_date(doc)),
            "value": "day %d/%d, night %d/%d mmHg: night %+d/%+d mmHg (systolic %+.1f%%, diastolic %+.1f%%)" % (
                ds, dd, ns, nd, ns - ds, nd - dd, 100 * (ns - ds) / ds, 100 * (nd - dd) / dd),
            "formula": "night-time mean minus daytime mean of the same 24-h report; percentages use the daytime mean; "
                       "not pooled with admission readings or peaks; no clinical classification",
            "passages": list(dict.fromkeys((day.get("passage_ids") or []) + (night.get("passage_ids") or [])))})
    return lines


def add_statistics(store, card, primary, spec, as_of):
    """Append the slot's statistics to card['computed_lines'] (slot_map 'stats'; dose change on medication cards)."""
    if card.get("status") == "not_documented":
        return card
    wanted = list(spec.get("stats") or [])
    if card.get("compute") in ("current_meds", "med_changes") and "daily_dose_change" not in wanted:
        wanted.append("daily_dose_change")
    lines = []
    for s in wanted:
        if s == "daily_dose_change":
            lines += daily_dose_change(store, primary)
        elif s == "bmi_check":
            lines += bmi_check(store, as_of)
        elif s == "bp_day_night":
            lines += bp_day_night(store, as_of)
    if lines:
        card["computed_lines"] = (card.get("computed_lines") or []) + lines
    return card
