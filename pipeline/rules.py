"""Rule extractors over document text (gaps IBM misses + structured parsing)."""
import re

from .ctx import fact, quote_span
from .meds import med_label, parse_med
from .vocab import ALLERGEN_EN, REACTION_EN, gloss

DEC = r"\d+(?:[.,]\d+)?"
LEFT_RE = re.compile(r"(?<![\wäöü])(links|linke[nrs]?|li\.|li|sin\.)(?![\wäöü])", re.I)
RIGHT_RE = re.compile(r"(?<![\wäöü])(rechts|rechte[nrs]?|re\.|dext\w*)(?![\wäöü])", re.I)


def side_near(text, s, e):
    best = None
    for rx, side in ((LEFT_RE, "left"), (RIGHT_RE, "right")):
        for m in rx.finditer(text):
            d = s - m.end() if m.end() <= s else (m.start() - e if m.start() >= e else 0)
            if best is None or d < best[0]:
                best = (d, side)
    return best[1] if best else None


def q(p, s, e, maxlen=220):
    a, b = quote_span(p["text"], s, e, maxlen)
    return p["text"][a:b]


def fmt_num(v):
    return v.replace(",", ".")


# ---------------------------------------------------------------- allergies
ALLERGY_RE = re.compile(r"\b(KM|Kontrastmittel|Penicillin|Jod|Latex)[- ]?Allergie", re.I)


def r_allergies(ctx, p, out):
    for m in ALLERGY_RE.finditer(p["text"]):
        quote = q(p, m.start(), m.end(), maxlen=160)
        allergen = ALLERGEN_EN.get(m.group(1).lower(), m.group(1))
        tail = p["text"][m.end():]
        tail = re.split(r"[.;]|\)\s*,", tail)[0] if tail else ""
        reactions = []
        for de, en in REACTION_EN.items():
            mm = re.search(r"\b" + de, tail, re.I)
            if mm and m.end() + mm.end() <= p["text"].find(quote) + len(quote) + 1:
                reactions.append((mm.start(), en))
        reactions = [en for _, en in sorted(reactions)]
        label = "%s%s allergy" % (allergen[:1].upper(), allergen[1:])
        if reactions:
            label += " (%s)" % ", ".join(reactions)
        ctxt = "allergy list" if (p["section"] or "").lower().startswith("allergie") else None
        if re.search(r"bekannt", quote, re.I):
            label = "Known " + label[:1].lower() + label[1:]
        if re.search(r"bei letzter Untersuchung", quote):
            label += " at last examination"
        d, pr = ctx.date_for(p)
        out.append(fact(p, quote, "allergies", "allergy", label,
                        {"substance": allergen, "reactions": reactions, "context": ctxt},
                        status=ctx.era_status(p), date=d, precision=pr))


def r_noncontrast_ct(ctx, p, out):
    t = p["text"]
    sec = p["section"] or ""
    m = re.search(r"Schädel-CT", t)
    if m and re.search(r"\bnativ\b", t):
        s = m.start()
        e = t.find(")", s) + 1 if ")" in t[s:] else m.end()
        quote = t[s:e] if len(t) > 160 else t
        label = "Head CT performed without contrast (native)"
        if re.search(r"KM-Allergie", quote):
            label += " because of known contrast media allergy"
        d, pr = ctx.date_for(p)
        out.append(fact(p, quote, "procedures", "imaging", label, {"contrast": "none"},
                        status="historical", date=d, precision=pr))
    elif re.search(r"Schädel-CT", sec) and re.search(r"\bnativ\b", t):
        d, pr = ctx.date_for(p)
        out.append(fact(p, t, "procedures", "imaging", "Head CT: non-contrast (native) series",
                        {"contrast": "none"}, status="historical", date=d, precision=pr))


# ---------------------------------------------------------------- vitals
VITALS = [
    ("height", re.compile(r"Größe:?\s*(" + DEC + r")\s*(cm|m)\b"), "Height", None),
    ("weight", re.compile(r"Gewicht:?\s*(" + DEC + r")\s*(kg)\b"), "Weight", None),
    ("bmi", re.compile(r"BMI:?\s*(" + DEC + r")(?!\d)"), "BMI", "kg/m²"),
    ("temperature", re.compile(r"Körpertemperatur:?\s*(" + DEC + r")\s*(°C)"), "Body temperature", None),
    ("heart_rate", re.compile(r"\bHF:?\s*(\d+)\s*(/min)"), "Heart rate", None),
]
BP_RE = re.compile(r"(?<![\d/.,])(\d{2,3})/(\d{2,3})(?![\d/])(\s*mm\s?Hg)?")


def r_vitals(ctx, p, out):
    t = p["text"]
    d, pr = ctx.date_for(p)
    st = ctx.era_status(p)
    for cat, rx, name, unit_default in VITALS:
        for m in rx.finditer(t):
            val = m.group(1)
            unit = (m.group(2) if m.lastindex and m.lastindex >= 2 else None) or unit_default
            label = "%s %s %s" % (name, fmt_num(val), unit or "")
            extra = {}
            if cat == "heart_rate":
                tail = t[m.end():m.end() + 30]
                if re.search(r"Normaltyp", tail):
                    label += ", ECG normal axis"
                    extra["ecg_axis"] = "normal"
            out.append(fact(p, q(p, m.start(), m.end(), 120), "vital_signs", cat, label,
                            dict({"value": fmt_num(val), "unit": unit}, **extra), status=st, date=d, precision=pr))
    # heart-rate range (Holter)
    m = re.search(r"Sinusrhythmus mit HF von (\d+)\s*-\s*(\d+)\s*\((\d+)\)/min", t)
    if m:
        out.append(fact(p, t, "results", "heart_rate",
                        "Holter ECG: sinus rhythm throughout, heart rate %s-%s/min (mean %s)" % m.groups(),
                        {"value": "%s-%s" % (m.group(1), m.group(2)), "unit": "/min", "mean": m.group(3)},
                        status=st, date=d, precision=pr))
    # blood pressure
    sec = p["section"] or ""
    bp_ctx = re.search(r"RR|mmHg|Blutdruck|mittelwert", t + " " + sec, re.I)
    if bp_ctx:
        for m in BP_RE.finditer(t):
            if re.match(r"\d", t[m.end():m.end() + 1] or "x"):
                continue
            pre = t[max(0, m.start() - 60):m.start()]
            if re.search(r"MMSE", pre[-12:]):
                continue
            qual = []
            if re.search(r"24-?Mittelwert", pre):
                qual.append("24h mean")
            elif re.search(r"Tagesmittelwert", pre):
                qual.append("daytime mean")
            elif re.search(r"Nachtmittelwert", pre):
                qual.append("night-time mean")
            if re.search(r"Morgen|morgendlich", pre):
                qual.append("morning peaks")
            if re.search(r"bis\s*$", pre):
                qual.append("up to")
            if re.search(r"Entgleisung", pre):
                qual.append("hypertensive derailment")
            if re.search(r"Aufnahme", pre + sec):
                qual.append("on admission")
            if re.search(r"normalisiert|eingestellt", t[m.end():m.end() + 30] + pre[-30:]):
                qual.append("after treatment")
            label = "Blood pressure %s/%s mmHg" % (m.group(1), m.group(2))
            if qual:
                label += " (%s)" % ", ".join(qual)
            out.append(fact(p, q(p, m.start(), m.end(), 120), "vital_signs", "blood_pressure", label,
                            {"value": "%s/%s" % (m.group(1), m.group(2)), "unit": "mmHg", "context": ", ".join(qual)},
                            status=st, date=d, precision=pr))
    m = re.search(r"MMSE:?\s*(\d+)\s*/\s*(\d+)", t)
    if m:
        out.append(fact(p, t[m.start():m.end()], "functional_status", "mmse",
                        "MMSE %s/%s" % m.groups(), {"value": m.group(1), "max": m.group(2)},
                        status=st, date=d, precision=pr))
    m = re.search(r"(\d+)-jährige", t)
    if m:
        out.append(fact(p, q(p, m.start(), m.end(), 120), "social_history", "age",
                        "Age %s years at the time of the document" % m.group(1), {"value": m.group(1), "unit": "years"},
                        status="historical", date=d, precision=pr))
    if re.search(r"gutem (AZ|Allgemeinzustand)", t):
        mm = re.search(r"gutem (AZ|Allgemeinzustand)", t)
        out.append(fact(p, q(p, mm.start(), mm.end(), 120), "functional_status", "general_condition",
                        "Good general condition", {}, status=st, date=d, precision=pr))


# ---------------------------------------------------------------- cardiology results
def r_cardio(ctx, p, out):
    t = p["text"]
    d, pr = ctx.date_for(p)
    st = ctx.era_status(p)
    m = re.search(r"\bEF\s*(\d+)\s*%", t)
    if m:
        label = "LVEF %s%%" % m.group(1)
        attrs = {"value": m.group(1), "unit": "%"}
        if re.search(r"normale systolische LV-Funktion", t, re.I):
            label += ", normal systolic LV function"
            attrs["interpretation"] = "normal systolic LV function"
        out.append(fact(p, q(p, m.start(), m.end()), "results", "lv_function", label, attrs,
                        status=st, date=d, precision=pr))
    m = re.search(r"leichte Verdickung des linken Ventrikels", t)
    if m:
        out.append(fact(p, t, "results", "echo", "Echocardiography: mild left ventricular thickening", {},
                        status=st, date=d, precision=pr))
    m = re.search(r"Normale diastolische Funktion", t)
    if m:
        out.append(fact(p, t[m.start():m.end()], "results", "echo", "Echocardiography: normal diastolic function",
                        {}, status=st, date=d, precision=pr))
    m = re.search(r"Normale rechtsventrikuläre Funktion\s*\(TAPSE\s*(\d+)\s*mm\)", t)
    if m:
        out.append(fact(p, t[m.start():m.end()], "results", "echo",
                        "Echocardiography: normal right ventricular function (TAPSE %s mm)" % m.group(1),
                        {"value": m.group(1), "unit": "mm"}, status=st, date=d, precision=pr))
    m = re.search(r"PAP\s*(\d+)\s*mm\s?Hg", t)
    if m:
        out.append(fact(p, q(p, m.start(), m.end()), "results", "echo",
                        "Estimated systolic pulmonary artery pressure %s mmHg, no evidence of pulmonary hypertension" % m.group(1)
                        if re.search(r"kein Anhalt für pulmonale Hypertonie", t) else
                        "Estimated systolic pulmonary artery pressure %s mmHg" % m.group(1),
                        {"value": m.group(1), "unit": "mmHg"}, status=st, date=d, precision=pr))
    m = re.search(r"keine fokalneurologischen Ausfälle", t)
    if m:
        out.append(fact(p, t, "results", "neurological_exam", "No focal neurological deficits on admission",
                        {}, status=st, date=d, precision=pr))


def r_hba1c(ctx, p, out):
    for m in re.finditer(r"HbA1c(?:\s+von)?\s*(" + DEC + r")\s*%", p["text"]):
        # tighten to clause (comma / parentheses) for long lines
        t = p["text"]
        lo = max(t.rfind("(", 0, m.start()), t.rfind(",", 0, m.start()), t.rfind(". ", 0, m.start()), -1)
        hi_c = [i for i in (t.find(")", m.end()), t.find(",", m.end())) if i != -1]
        hi = min(hi_c) if hi_c else len(t)
        quote = t[lo + 1:hi].strip()
        label = "HbA1c %s%%" % fmt_num(m.group(1))
        if re.search(r"gut eingestellt", quote, re.I):
            label += " (well-controlled type II diabetes)"
        d, pr = ctx.date_for(p)
        out.append(fact(p, quote, "results", "hba1c", label, {"value": fmt_num(m.group(1)), "unit": "%"},
                        status=ctx.era_status(p), date=d, precision=pr))


# ---------------------------------------------------------------- histology / oncology
HISTO_RE = re.compile(r"invasiv(?:e[sn]?)?\s+duktal\w*\s+Mammakarzinom\w*", re.I)
TNM_RE = re.compile(r"\b(T[0-4x][a-d]?)\s+(N[0-3x][a-c]?)\s+(M[01x])(?:\s+(V[01x]))?(?:\s+(L[01x]))?(?:\s+(G[1-3x]))?")
REC_RE = re.compile(r"(Östrogenrezeptor|Progesteronrezeptor):?\s*(positiv|negativ)\s*(?:\((\d+)\s*%[^)]*\))?\s*(?:Allred-Score:?\s*(\d+))?", re.I)
HER2_RE = re.compile(r"Her-?2(?:neu)?(?:-Expression)?:?\s*(positiv|negativ)", re.I)
HR_RE = re.compile(r"Hormonrezeptor(?:status)?:?\s+(positiv|negativ)", re.I)
KI67_RE = re.compile(r"Ki-?67(?:-Proliferationsrate)?:?\s*(\d+)\s*%", re.I)
POSNEG = {"positiv": "positive", "negativ": "negative"}


def r_histology(ctx, p, out):
    t = p["text"]
    d, pr = ctx.date_for(p)
    st = ctx.era_status(p)
    for m in HISTO_RE.finditer(t):
        side = side_near(t, m.start(), m.end()) if re.search(r"Brust|Mamma", t) else None
        label = "Invasive ductal carcinoma of the breast" + (" (%s)" % side if side else "")
        out.append(fact(p, q(p, m.start(), m.end(), 160), "results", "histology", label,
                        {"histotype": "invasive ductal carcinoma", "side": side}, status=st, date=d, precision=pr))
    for m in TNM_RE.finditer(t):
        parts = [g for g in m.groups() if g]
        attrs = {g[0]: g[1:] for g in parts}
        out.append(fact(p, t[m.start():m.end()], "results", "tnm", "TNM: " + " ".join(parts), attrs,
                        status=st, date=d, precision=pr))
    for m in REC_RE.finditer(t):
        rec = "Oestrogen receptor" if m.group(1).lower().startswith("ö") else "Progesterone receptor"
        label = "%s %s" % (rec, POSNEG[m.group(2).lower()])
        det = []
        if m.group(3):
            det.append("%s%% of tumour cells" % m.group(3))
        if m.group(4):
            det.append("Allred %s" % m.group(4))
        if det:
            label += " (%s)" % ", ".join(det)
        out.append(fact(p, t[m.start():m.end()].strip(), "results", "receptor_status", label,
                        {"receptor": "ER" if rec.startswith("O") else "PR", "result": POSNEG[m.group(2).lower()],
                         "value": m.group(3), "unit": "%" if m.group(3) else None, "allred": m.group(4)},
                        status=st, date=d, precision=pr))
    for m in HER2_RE.finditer(t):
        out.append(fact(p, t[m.start():m.end()], "results", "receptor_status", "HER2 %s" % POSNEG[m.group(1).lower()],
                        {"receptor": "HER2", "result": POSNEG[m.group(1).lower()]}, status=st, date=d, precision=pr))
    for m in HR_RE.finditer(t):
        out.append(fact(p, t[m.start():m.end()], "results", "receptor_status",
                        "Hormone receptor %s" % POSNEG[m.group(1).lower()],
                        {"receptor": "HR", "result": POSNEG[m.group(1).lower()]}, status=st, date=d, precision=pr))
    for m in KI67_RE.finditer(t):
        out.append(fact(p, t[m.start():m.end()], "results", "ki67", "Ki-67 proliferation rate %s%%" % m.group(1),
                        {"value": m.group(1), "unit": "%"}, status=st, date=d, precision=pr))
    # tumour / lesion size
    for m in re.finditer(r"Ausdehnung\s+(" + DEC + r")\s*x\s*(" + DEC + r")\s*cm", t):
        out.append(fact(p, q(p, m.start(), m.end(), 160), "results", "tumour_size",
                        "Breast lesion maximum extent %s x %s cm (ultrasound)" % (fmt_num(m.group(1)), fmt_num(m.group(2))),
                        {"value": "%s x %s" % (fmt_num(m.group(1)), fmt_num(m.group(2))), "unit": "cm"},
                        status=st, date=d, precision=pr))
    m = re.search(r"\bals\s+(" + DEC + r")\s*cm\s+beschrieben", t)
    if m:
        prev = _prev_text(ctx, p)
        if re.search(r"Ausdehnung des Tumors", prev + " " + t):
            out.append(fact(p, q(p, m.start(), m.end(), 160), "results", "tumour_size",
                            "Tumour extent described as %s cm (external mammography report)" % fmt_num(m.group(1)),
                            {"value": fmt_num(m.group(1)), "unit": "cm"}, status=st, date=d, precision=pr))
    m = re.search(r"Knoten im (äußeren|inneren) (oberen|unteren) Quadranten", t)
    if m:
        en = {"äußeren": "outer", "inneren": "inner", "oberen": "upper", "unteren": "lower"}
        out.append(fact(p, q(p, m.start(), m.end(), 160), "results", "clinical_exam",
                        "Palpable lump in the %s %s quadrant" % (en[m.group(2)], en[m.group(1)]), {},
                        status=st, date=d, precision=pr))
    for m in re.finditer(r"(keine\s+)?vergrößerte[n]?\s+Lymphknoten(\s+(?:rechts|links))?(\s+axillär)?", t):
        neg = bool(m.group(1)) or bool(re.search(r"\bkeine\s+vergrößerten", t))
        side = None
        if m.group(2):
            side = "right" if "rechts" in m.group(2) else "left"
        axillary = bool(m.group(3)) or bool(re.search(r"axillär", t))
        how = "ultrasound" if re.search(r"Sonograph", t) else ("palpation" if re.search(r"Tastbefund|tastbar", t + _prev_text(ctx, p)) else None)
        label = ("No enlarged" if neg else "Enlarged") + (" axillary" if axillary else "") + " lymph nodes"
        if side:
            label += ", %s" % side
        if how:
            label += " (%s)" % how
        out.append(fact(p, q(p, m.start(), m.end(), 160), "results", "lymph_nodes", label,
                        {"side": side, "finding": "not enlarged" if neg else "enlarged", "method": how},
                        status=st, date=d, precision=pr))
    m = re.search(r"BI-?RADS\s*([0-6]|[IV]+)\b", t)
    if m:
        out.append(fact(p, t[m.start():m.end()], "results", "birads", "BI-RADS %s" % m.group(1),
                        {"value": m.group(1)}, status=st, date=d, precision=pr))
    m = re.search(r"\bACR\s*([IV]+|[1-4])\b", t)
    if m:
        out.append(fact(p, t[m.start():m.end()], "results", "breast_density", "Breast density ACR %s" % m.group(1),
                        {"value": m.group(1)}, status=st, date=d, precision=pr))


def _prev_text(ctx, p):
    doc = ctx.docs[p["doc_id"]]
    i = doc.passages.index(p)
    return doc.passages[i - 1]["text"] if i > 0 else ""


# ---------------------------------------------------------------- plans and follow-ups
def r_plans(ctx, p, out):
    t = p["text"]
    sec = (p["section"] or "").lower()
    d, pr = ctx.date_for(p, t, explicit=True)
    surg = []
    if re.search(r"Quadrantenresektion", t):
        surg.append("quadrantectomy")
    if re.search(r"intraoperativ\w* Bestrahlung|\bIORT\b", t):
        surg.append("intraoperative radiotherapy (IORT)")
    if re.search(r"Tumorboard", t) and re.search(r"empfohlen|empfiehlt", t) and surg:
        m = re.search(r"Tumorboard", t)
        a = t.rfind(". ", 0, m.start())
        out.append(fact(p, t[a + 1 if a != -1 else 0:].strip(), "plan_of_care", "planned_procedure",
                        "Tumour board recommendation: " + " with ".join(surg),
                        {"procedures": surg, "decided_by": "tumour board"}, status="recommended",
                        date=ctx.date_for(p)[0], precision="day"))
    if "procedere" in sec:
        dates = [x for x in re.finditer(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", t)]
        if surg:
            label = "Planned " + " + ".join(surg)
            if dates:
                dm = dates[0]
                label += " on %s" % dm.group(0)
            if re.search(r"chirurgischen Abteilung", t):
                label += " (surgical department)"
            out.append(fact(p, t, "plan_of_care", "planned_procedure", label, {"procedures": surg},
                            status="planned", date=d, precision=pr))
        elif re.search(r"Stationäre Aufnahme", t):
            label = "Planned inpatient admission" + (" on %s" % dates[0].group(0) if dates else "")
            out.append(fact(p, t, "plan_of_care", "planned_admission", label, {}, status="planned",
                            date=d, precision=pr))
        elif re.search(r"geplant", t):
            out.append(fact(p, t, "plan_of_care", "planned_procedure",
                            "Planned: " + re.sub(r"\s*planned$", "", gloss(t)), {},
                            status="planned", date=ctx.docs[p["doc_id"]].date, precision="day"))
        elif re.search(r"Tumorboard", t):
            out.append(fact(p, t, "plan_of_care", "planned_procedure",
                            "Further management to be discussed at the tumour board", {}, status="planned",
                            date=ctx.docs[p["doc_id"]].date, precision="day"))


def r_followups(ctx, p, out):
    t = p["text"]
    d, pr = ctx.date_for(p)
    m = re.search(r"(Duplex\w*|Doppler\w*)[^.]*?\bin\s+(\d+)\s+(Monaten|Wochen|Tagen)", t)
    if m:
        unit = {"Monaten": "months", "Wochen": "weeks", "Tagen": "days"}[m.group(3)]
        target = "carotid duplex ultrasound" if re.search(r"Karotis|Carotis", t) else "duplex ultrasound"
        out.append(fact(p, q(p, m.start(), m.end()), "plan_of_care", "followup",
                        "Follow-up %s in %s %s" % (target, m.group(2), unit),
                        {"test": target, "interval": "%s %s" % (m.group(2), unit)}, status="recommended",
                        date=d, precision=pr))
    m = re.search(r"Regelmäßige (augenärztliche Kontrollen|Augenkontrollen)", t)
    if m:
        out.append(fact(p, q(p, m.start(), m.end()), "plan_of_care", "followup",
                        "Regular ophthalmology (eye) check-ups recommended", {"test": "eye check-ups"},
                        status="recommended", date=d, precision=pr))
    m = re.search(r"Regelmäßige Blutdruckkontrollen", t)
    if m:
        label = "Regular blood pressure checks"
        if re.search(r"Anpassung der Medikation", t):
            label += " and further adjustment of medication"
        if re.search(r"Hausarzt", t):
            label += " by the GP"
        out.append(fact(p, q(p, m.start(), m.end()), "plan_of_care", "followup", label,
                        {"test": "blood pressure checks", "responsible": "GP" if "Hausarzt" in t else None},
                        status="recommended", date=d, precision=pr))


# ---------------------------------------------------------------- carotid findings
CAROTID_RE = re.compile(r"carotis|karotis", re.I)
STEN_RE = re.compile(r"Abgangsstenose|Stenose|Karotisstenose|Carotisstenose|Einengung|Carotissklerose|Karotissklerose", re.I)


def r_carotid(ctx, p, out):
    t = p["text"]
    if not CAROTID_RE.search(t):
        return
    if re.search(r"Fragestellung", t) and not re.search(r"\d+\s*%", t):
        return
    if re.search(r"zurückgeführt", t):
        return  # handled as attributed cause
    d, pr = ctx.date_for(p)
    st = ctx.era_status(p)
    sec = p["section"] or ""
    m = STEN_RE.search(t)
    pm = re.search(r"(\d+)\s*%", t)
    if m and (pm or re.search(r"stenose", m.group(0), re.I)):
        side = side_near(t, m.start(), m.end())
        lead = re.match(r"\s*(Links|Rechts)\b", t)
        if lead:
            side = "left" if lead.group(1) == "Links" else "right"
        ips = "problems" if re.match(r"diagnose", sec, re.I) or re.match(r"Diagnose:", t) else "results"
        if re.search(r"Duplex|Doppler", sec + " " + t):
            source = "carotid duplex/Doppler ultrasound"
        elif re.match(r"diagnose", sec, re.I) or re.match(r"Diagnose:", t):
            source = "diagnosis"
        else:
            source = None
        pct = pm.group(1) if pm else None
        kind = "sclerosis" if re.search(r"sklerose", m.group(0), re.I) else "stenosis"
        label = "Carotid artery %s" % kind
        if re.search(r"interna", t):
            label = "Internal carotid artery %s" % kind
        bits = [b for b in (side, ("%s%%" % pct) if pct else None) if b]
        if bits:
            label += ", " + ", ".join(bits)
        if source and source != "diagnosis":
            label += " (%s)" % source
        out.append(fact(p, q(p, m.start(), m.end()), ips, "carotid_stenosis", label,
                        {"side": side, "value": pct, "unit": "%" if pct else None, "source": source,
                         "section": None}, status=st, date=d, precision=pr))
    pl = re.search(r"Plaquebildungen ohne hämodynamische Wirksamkeit", t)
    if pl:
        side = side_near(t, pl.start(), pl.end())
        lead = re.search(r"Auf der (linken|rechten) Seite", t)
        if lead:
            side = "left" if lead.group(1) == "linken" else "right"
        out.append(fact(p, q(p, pl.start(), pl.end()), "results", "carotid_plaque",
                        "Minimal calcified carotid plaques without haemodynamic significance" + (", %s" % side if side else ""),
                        {"side": side}, status=st, date=d, precision=pr))
    br = re.search(r"Strömungsgeräusch über der (linken|rechten) Karotis", t)
    if br:
        side = "left" if br.group(1) == "linken" else "right"
        out.append(fact(p, q(p, br.start(), br.end()), "results", "carotid_bruit",
                        "Faint bruit over the %s carotid on auscultation" % side, {"side": side},
                        status=st, date=d, precision=pr))


# ---------------------------------------------------------------- diagnoses / events / misc
def r_diagnoses(ctx, p, out):
    t = p["text"]
    sec = p["section"] or ""
    d, pr = ctx.date_for(p)
    st = ctx.era_status(p)
    unknown = set()
    if re.match(r"diagnosen?:", sec, re.I) and t != sec and p["kind"] == "line" and not CAROTID_RE.search(t):
        label = gloss(t, unknown)
        hist = bool(re.match(r"\s*(St\.\s?p\.|Z\.\s?n\.)", t))
        susp = bool(re.match(r"\s*(Vd\.\s?a\.|Verdacht)", t))
        out.append(fact(p, t, "past_illness" if hist else "problems",
                        "carotid_stenosis" if CAROTID_RE.search(t) else "diagnosis", label,
                        {"assertion": "statuspost" if hist else ("suspected" if susp else "positive"),
                         "context": "diagnosis list"},
                        status="historical" if hist else st, date=d, precision=pr))
    elif re.match(r"Diagnose:", t):
        out.append(fact(p, t, "problems", "diagnosis", gloss(t, unknown),
                        {"assertion": "positive", "context": "diagnosis"}, status=st, date=d, precision=pr))
    m = re.match(r"Einweisungsdiagnose", t)
    if m:
        out.append(fact(p, t, "problems", "presenting_event", gloss(t, unknown),
                        {"assertion": "positive", "context": "admission diagnosis"}, status=st, date=d, precision=pr))
    m = re.search(r"wurde (?:die|der|das)\s+(.+?)\s+auf (?:eine[nr]?\s+)?(.+?)\s+zurückgeführt", t)
    if m:
        out.append(fact(p, t[:m.end()].strip() if len(t) > 220 else t, "problems", "attributed_cause",
                        "%s attributed to %s" % (gloss(m.group(1), unknown), gloss(m.group(2), unknown).lower()),
                        {"symptoms": gloss(m.group(1)).lower(), "cause": gloss(m.group(2)).lower()},
                        status=st, date=d, precision=pr))
    m = re.search(r"aufgrund einer\s+hypertensiven Krise mit (.+?) zur weiteren Abklärung aufgenommen", t)
    if m:
        out.append(fact(p, t, "problems", "presenting_event",
                        "Admitted because of hypertensive crisis with malaise, vertigo and brief partial vision loss"
                        if re.search(r"Unwohlsein", m.group(1)) and re.search(r"Sehverlust", m.group(1))
                        else "Admitted because of hypertensive crisis", {}, status=st, date=d, precision=pr))
    if re.search(r"Familienanamnestisch ist keine Vorbelastung", t):
        out.append(fact(p, t, "social_history", "family_history", "No known relevant family history", {},
                        status=st, date=d, precision=pr))
    if re.search(r"durch ihre Familie gut unterstützt", t):
        mm = re.search(r"durch ihre Familie gut unterstützt", t)
        out.append(fact(p, q(p, mm.start(), mm.end()), "social_history", "social_support",
                        "Well supported by her family", {}, status=st, date=d, precision=pr))
    return unknown


DOB_RE = re.compile(r"geb\.?\s*(?:am\s*)?(\d{2}\.\d{2}\.\d{4})")


def r_encounters(ctx, p, out):
    t = p["text"]
    m = re.search(r"Aufnahme am\s+(\d{1,2}/\d{1,2}/\d+)\s*\|\s*Entlassen am\s+(\d{1,2}/\d{1,2}/\d+)", t)
    if m:
        doc = ctx.docs[p["doc_id"]]
        label = "Inpatient stay: admitted %s, discharged %s" % m.groups()
        if not doc.stay_discharge:
            label += " (discharge date as written, not a valid date)"
        out.append(fact(p, t[m.start():m.end()], "past_illness", "encounter", label,
                        {"admission": m.group(1), "discharge": m.group(2)}, status="historical",
                        date=doc.stay_admission or doc.date, precision="day"))
    m = re.search(r"wurde am\s+(\d{1,2}\.\d{1,2}\.\d{4})\s.*?aufgenommen", t)
    if m:
        dt = [x for x in ctx.date_for(p, m.group(1), explicit=True)]
        out.append(fact(p, q(p, m.start(), m.end()), "past_illness", "encounter",
                        "Admitted on %s" % m.group(1), {"event": "admission", "date_text": m.group(1)},
                        status="historical", date=dt[0], precision=dt[1]))
    m = re.search(r"am\s+(\d{1,2}\.\d{1,2}\.\d{4})\s.*?entlassen", t)
    if m:
        dt = ctx.date_for(p, m.group(1), explicit=True)
        out.append(fact(p, q(p, m.start(), m.end()), "past_illness", "encounter",
                        "Discharged on %s" % m.group(1), {"event": "discharge", "date_text": m.group(1)},
                        status="historical", date=dt[0], precision=dt[1]))
    m = re.search(r"welche am\s+(\d{1,2}\.\d{1,2}\.\d{4})\s.*?Behandlung", t)
    if m:
        dt = ctx.date_for(p, m.group(1), explicit=True)
        out.append(fact(p, q(p, m.start(), m.end()), "past_illness", "encounter",
                        "Outpatient visit on %s" % m.group(1), {"event": "outpatient visit", "date_text": m.group(1)},
                        status="historical", date=dt[0], precision=dt[1]))
    m = re.search(r"Mammog\w*\s+vom\s+(\d{1,2}\.\s*\w+\s+\d{4})", t)
    if m:
        dt = ctx.date_for(p, m.group(0), explicit=True)
        out.append(fact(p, q(p, m.start(), m.end()), "procedures", "imaging",
                        "External mammography dated %s" % m.group(1),
                        {"date_text": m.group(1)}, status="historical", date=dt[0], precision=dt[1]))
    m = re.search(r"Mammographie\s+(Anfang|Mitte|Ende)\s+(\w+)\s+(\d{4})", t)
    if m:
        dt = ctx.date_for(p, None, explicit=True)
        en = {"Anfang": "early", "Mitte": "mid", "Ende": "late"}[m.group(1)]
        out.append(fact(p, q(p, m.start(), m.end()), "procedures", "imaging",
                        "Screening mammography in %s %s %s" % (en, m.group(2), m.group(3)),
                        {"date_text": "%s %s %s" % m.groups()}, status="historical", date=dt[0], precision=dt[1]))


def r_biopsy(ctx, p, out):
    t = p["text"]
    m = re.match(r"Entnahmedatum:?\s*(\d{1,2}\.\d{1,2}\.\d{4})", t)
    if m:
        doc = ctx.docs[p["doc_id"]]
        technique = "core biopsy" if re.search(r"Entnahmetechnik:?\s*Stanzbiopsie", doc.text) else "biopsy"
        dt = ctx.date_for(p, t, explicit=True)
        out.append(fact(p, t, "procedures", "biopsy", "Specimen collection (%s) on %s" % (technique, m.group(1)),
                        {"technique": technique, "date_text": m.group(1)}, status="historical",
                        date=dt[0], precision=dt[1]))
    m = re.search(r"(ultraschallgezielte|sonographisch gezielte)\s+Biopsie(?:\s+von\s+(\d+)\s+Stanzzylindern)?", t)
    if m:
        label = "Ultrasound-guided core biopsy"
        if m.group(2):
            label += " (%s cores)" % m.group(2)
        d, pr = ctx.date_for(p)
        out.append(fact(p, q(p, m.start(), m.end()), "procedures", "biopsy", label,
                        {"technique": "ultrasound-guided core biopsy", "cores": m.group(2)}, status="historical",
                        date=d, precision=pr))
    m = re.match(r"Fall(?:-ID|zahl)?:\s*(\d{6,})\s*$", t)
    if m:
        d, pr = ctx.docs[p["doc_id"]].date, "day"
        out.append(fact(p, t, "past_illness", "case_number", "Case (Fall) number %s" % m.group(1),
                        {"value": m.group(1)}, status="historical", date=d, precision=pr))


def r_meds(ctx, p, out):
    t = p["text"]
    if p["kind"] == "table_row":
        a = parse_med(t)
        if not a:
            return
        cat = a.pop("category", None) or "other_medication"
        d, pr = ctx.date_for(p)
        out.append(fact(p, t, "medications", cat, med_label(a), a, status=ctx.med_status(p), date=d, precision=pr))
        return


RULES = [r_allergies, r_noncontrast_ct, r_vitals, r_cardio, r_hba1c, r_histology, r_plans, r_followups,
         r_carotid, r_diagnoses, r_encounters, r_biopsy, r_meds]


def run_rules(ctx):
    out = []
    unknown = set()
    for doc in ctx.docs.values():
        for p in doc.passages:
            for r in RULES:
                res = r(ctx, p, out)
                if isinstance(res, set):
                    unknown |= res
    # date of birth: one fact linked to all passages carrying it
    dob = {}
    for doc in ctx.docs.values():
        for p in doc.passages:
            m = DOB_RE.search(p["text"]) or re.search(r"geb\s+(\d{2}\.\d{2}\.\d{4})", p["text"])
            if m:
                dob.setdefault(m.group(1), []).append(p)
    for val, ps in dob.items():
        f = fact(ps[-1], val, "social_history", "date_of_birth", "Date of birth %s" % val, {"value": val},
                 status="current", date=None, precision="day")
        f["passage_ids"] = [x["id"] for x in ps]
        f["date"] = ctx.docs[ps[-1]["doc_id"]].date
        out.append(f)
    return out, unknown
