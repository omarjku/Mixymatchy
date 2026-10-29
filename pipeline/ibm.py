"""IBM linker: map every IBM mention to an exact passage span and create origin=ibm facts."""
import os
import re

from .common import PATIENT_DIR, clean_ibm_text, find_dates, find_ws, load_json
from .ctx import fact
from .meds import med_label, parse_med
from .vocab import INGREDIENT_EN, MEL_EN, atc_category, gloss

SYSTEM = {"ATC": "ATC", "ICD10": "ICD-10", "ICD-10": "ICD-10", "MEL": "MEL"}


def _code(node):
    c = node.get("code") if node else None
    if not c or not c.get("value"):
        return None
    return {"system": SYSTEM.get(c.get("catalog"), c.get("catalog")), "value": c["value"]}


def iter_mentions(tree):
    """Yield (mention, concept_node, ancestors)."""
    def walk(node, anc):
        for c in node.get("values", []) or []:
            if not isinstance(c, dict):
                continue
            if "text" in c and "documentIds" in c:
                yield c, node, anc
            else:
                yield from walk(c, anc + [node])
    yield from walk(tree, [])


class Linker:
    def __init__(self, ctx):
        self.ctx = ctx
        self.counters = {}
        self.unmatched = []
        self.matched = 0

    def locate(self, doc_id, text, concept_id, ibm_date=None):
        doc = self.ctx.docs.get(doc_id)
        if not doc:
            return None
        cands = []
        variants = [text]
        stripped = text.rstrip(".?:; ")
        if stripped != text:
            variants.append(stripped)
        for v in variants:
            for p in doc.passages:
                sp = find_ws(p["text"], v)
                if sp:
                    cands.append((p, sp))
            if cands:
                break
        if not cands:
            return None
        # prefer passages carrying the IBM day-precision date (e.g. "2016-04-13")
        if ibm_date and re.match(r"\d{4}-\d{2}-\d{2}$", ibm_date):
            dated = [c for c in cands if any(d == ibm_date for d, _, _ in
                                             find_dates(c[0]["text"] + " " + (c[0]["section"] or "")))]
            if dated:
                cands = dated
        key = (doc_id, " ".join(text.split()).lower(), concept_id)
        k = self.counters.get(key, 0)
        self.counters[key] = k + 1
        return cands[min(k, len(cands) - 1)]

    def link_all(self):
        facts = []
        facts += self.link_tree("medication")
        facts += self.link_tree("diagnoses")
        facts += self.link_tree("procedures")
        facts += self.link_scores()
        return facts

    def link_tree(self, name):
        tree = load_json(os.path.join(PATIENT_DIR, name + ".json"))
        out = []
        for men, concept, anc in iter_mentions(tree):
            text = clean_ibm_text(men["text"])
            ibm_date = (men.get("date") or {}).get("value")
            for doc_id in men["documentIds"]:
                hit = self.locate(doc_id, text, concept.get("id"), ibm_date)
                if not hit:
                    self.unmatched.append({"file": name, "doc_id": doc_id, "text": text, "id": men.get("id")})
                    continue
                self.matched += 1
                p, (s, e) = hit
                quote = p["text"][s:e]
                f = getattr(self, "fact_" + name)(men, concept, anc, p, quote)
                if f:
                    f["_ibm_ids"] = [men.get("id")]
                    out.append(f)
        return out

    # ---- medication
    def fact_medication(self, men, concept, anc, p, quote):
        ing = (men.get("agent") or concept.get("name") or "").lower()
        generic = INGREDIENT_EN.get(ing, ing)
        code = _code(concept)
        a = parse_med(quote, generic_hint=generic, brand_hint=men.get("drug")) or {"generic": generic}
        a.pop("category", None)
        a["generic"] = generic
        cat = atc_category(code["value"]) if code else None
        if not cat:
            cls = " ".join(x.get("name", "") for x in anc).lower()
            cat = "antithrombotic" if ("antithrombot" in cls or "thrombozyten" in ing) else "other_medication"
        label = med_label(a)
        if generic == "antiplatelet agent":
            label = "Antiplatelet therapy (platelet aggregation inhibition)"
        d, pr = self.ctx.date_for(p)
        return fact(p, quote, "medications", cat, label, a, status=self.ctx.med_status(p), date=d,
                    precision=pr, code=code, origin="ibm")

    # ---- diagnoses
    def fact_diagnoses(self, men, concept, anc, p, quote):
        status = concept.get("status") or "positive"
        code = _code(concept)
        label = gloss(quote) or gloss(concept.get("name", "")) or concept.get("name", "")
        low = label.lower()
        if status == "negative" and not re.match(r"(no|without)\b", low) and "not seen" not in low:
            label = "No " + label[:1].lower() + label[1:]
        elif status == "suspected" and not re.search(r"suspected|suspicious|question|\?", low):
            label = "Suspected " + label[:1].lower() + label[1:]
        elif status == "statuspost" and "history" not in low:
            label = "History of " + label[:1].lower() + label[1:]
        cv = code["value"] if code else ""
        cat = "carotid_stenosis" if cv.startswith("I65") else "diagnosis"
        ips = "past_illness" if status == "statuspost" else "problems"
        d, pr = self.ctx.date_for(p)
        st = "historical" if status == "statuspost" else self.ctx.era_status(p)
        return fact(p, quote, ips, cat, label, {"assertion": status}, status=st, date=d, precision=pr,
                    code=code, origin="ibm")

    # ---- procedures
    def fact_procedures(self, men, concept, anc, p, quote):
        status = concept.get("status") or "positive"
        code = _code(concept)
        label = gloss(quote) or (MEL_EN.get(code["value"]) if code else None) or concept.get("name", "")
        low = label.lower()
        if re.search(r"regular|next planned|check-ups", low) or (status == "recommended" and re.search(r"kontroll", quote, re.I)):
            ips, cat, st = "plan_of_care", "followup", "recommended"
        elif status == "recommended":
            ips, cat, st = "plan_of_care", "planned_procedure", "recommended"
        else:
            ips, cat, st = "procedures", "procedure", "historical"
        if re.search(r"therapy", low) and code is None:
            ips, cat = "procedures", "therapy"
        d, pr = self.ctx.date_for(p, quote, explicit=True)
        return fact(p, quote, ips, cat, label, {"assertion": status}, status=st, date=d, precision=pr,
                    code=code, origin="ibm")

    # ---- scores
    SCORE_SPECS = {
        "Blutdruck": ("vital_signs", "blood_pressure", "Blood pressure", None),
        "Body-Mass-Index": ("vital_signs", "bmi", "BMI", r"BMI:?\s*{v}"),
        "Ejektionsfraktion": ("results", "lv_function", "LVEF", r"EF\s*{v}\s*%"),
        "Gewicht": ("vital_signs", "weight", "Weight", r"Gewicht:?\s*{v}\s*kg"),
        "Größe": ("vital_signs", "height", "Height", r"Größe:?\s*{cm}\s*cm"),
        "HbA1c": ("results", "hba1c", "HbA1c", r"HbA1c(?:\s+von)?\s*{v}\s*%"),
        "Herzfrequenz": ("vital_signs", "heart_rate", "Heart rate", r"(?:HF:?\s*|HF von\s*){v}(?!\d)"),
        "Körpertemperatur": ("vital_signs", "temperature", "Body temperature", r"Körpertemperatur:?\s*{v}\s*°C"),
        "Mini Mental State Examination": ("functional_status", "mmse", "MMSE", r"MMSE:?\s*{v}\s*/\s*\d+"),
        "pulmonalarterieller Druck": ("results", "echo", "Estimated systolic pulmonary artery pressure", r"PAP\s*{v}\s*mm\s?Hg"),
        "BIRADS": ("results", "birads", "BI-RADS", r"BI-?RADS\s*(?:{v}|{roman})\b"),
    }
    ROMAN = {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V", "6": "VI"}

    def link_scores(self):
        data = load_json(os.path.join(PATIENT_DIR, "scores-all.json"))
        out = []
        for s in data.get("scores", []):
            name = s.get("name")
            spec = self.SCORE_SPECS.get(name)
            for v in s.get("values", []):
                val = str(v.get("value"))
                for doc_id in v.get("documentIds", []):
                    f = self._score_fact(name, spec, s.get("unit"), val, doc_id, v.get("id"))
                    if f:
                        out.append(f)
                        self.matched += 1
                    else:
                        self.unmatched.append({"file": "scores-all", "doc_id": doc_id, "text": "%s=%s" % (name, val),
                                               "id": v.get("id")})
        return out

    def _score_fact(self, name, spec, unit, val, doc_id, sid):
        doc = self.ctx.docs.get(doc_id)
        if not doc or not spec:
            return None
        ips, cat, en, pat = spec
        vre = re.escape(val).replace(",", "[.,]").replace(r"\-", r"\s*-\s*").replace("-", r"\s*-\s*")
        if name == "Blutdruck":
            a, b = val.split("|")
            rx = re.compile(r"(?<![\d/])" + a + "/" + b + r"(?![\d/])")
        else:
            cm = None
            if name == "Größe":
                try:
                    cm = str(int(round(float(val.replace(",", ".")) * 100)))
                except ValueError:
                    return None
            rx = re.compile(pat.format(v=vre + r"(?![.,]?\d)", cm=cm, roman=self.ROMAN.get(val, "XX")))
        key = (doc_id, name, val)
        hits = []
        for p in doc.passages:
            for m in rx.finditer(p["text"]):
                hits.append((p, m))
        if not hits:
            return None
        k = self.counters.get(key, 0)
        self.counters[key] = k + 1
        p, m = hits[min(k, len(hits) - 1)]
        quote = p["text"][m.start():m.end()]
        num = re.findall(r"\d+(?:[.,]\d+)?(?:\s*-\s*\d+)?|\d+/\d+|[IVX]+$", quote)
        shown = re.search(r"\d+/\d+", quote).group(0) if name == "Blutdruck" else (num[-1] if num else val)
        if name == "Mini Mental State Examination":
            shown = re.search(r"\d+\s*/\s*\d+", quote).group(0)
        if name == "Größe":
            shown, unit = re.search(r"(\d+)\s*cm", quote).group(1), "cm"
        if name == "BIRADS":
            shown = quote.split()[-1]
        unit = {"kg/m2": "kg/m²"}.get(unit, unit)
        label = "%s %s%s" % (en, shown.replace(",", "."), (" " + unit) if unit and unit not in ("Punkte",) else "")
        d, pr = self.ctx.date_for(p)
        f = fact(p, quote, ips, cat, label, {"value": shown.replace(",", "."), "unit": unit},
                 status=self.ctx.era_status(p), date=d, precision=pr, origin="ibm")
        f["_ibm_ids"] = [sid]
        return f
