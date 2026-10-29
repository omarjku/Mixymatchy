"""Lenient medication text parser (table rows and narrative mentions)."""
import re

from .vocab import BRAND_GENERIC, FORM_EN, GENERIC_CATEGORY

_BRANDS = sorted(BRAND_GENERIC, key=lambda bg: -len(bg[0]))
STRENGTH_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mg|mcg|µg|g|ml|IE)\b", re.I)
ROUTE_RE = re.compile(r"(?<![\w.])(oral|s\.c\.|i\.v\.|p\.o\.)(?!\w)", re.I)
SCHED4_RE = re.compile(r"(?<![\d/.,])(\d+(?:/\d+)?)\s+(\d+(?:/\d+)?)\s+(\d+(?:/\d+)?)\s+(\d+(?:/\d+)?)(?![\d/.,])")
SCHED_DASH_RE = re.compile(r"(?<![\d-])(\d+(?:/\d+)?)-(\d+(?:/\d+)?)-(\d+(?:/\d+)?)(?:-(\d+(?:/\d+)?))?(?![\d-])")
WEEKLY_RE = re.compile(r"(\d+)\s*x\s*/\s*Woche", re.I)
DAILY_RE = re.compile(r"(\d+)\s*x\s*(?:/\s*)?(?:tgl\.|täglich|/Tag)", re.I)
PUFFS_RE = re.compile(r"(\d+)\s*Hüben?\b|(\d+)\s*Hübe\b", re.I)
TIME_WORDS = [(re.compile(r"\bmorgens\b", re.I), "in the morning"),
              (re.compile(r"\bmittags\b", re.I), "at midday"),
              (re.compile(r"\babends\b", re.I), "in the evening"),
              (re.compile(r"\bnachts\b|\bzur nacht\b", re.I), "at night")]
FORM_RE = re.compile(r"\b(Tropfen|Injektionslösung|Tabl\.|Spray)", re.I)


def find_brand(text):
    best = None
    for brand, generic in _BRANDS:
        m = re.search(r"(?<![\w])" + re.escape(brand).replace(r"\ ", r"\s*") + r"(?![\w])", text, re.I)
        if m and (best is None or m.start() < best[2]):
            best = (brand, generic, m.start(), m.end())
    return best


def parse_med(text, generic_hint=None, brand_hint=None):
    """Parse a medication mention. Returns dict or None when no drug can be identified."""
    b = find_brand(text)
    if b:
        brand, generic, bs, be = b
        brand_text = text[bs:be]
    else:
        if not generic_hint:
            return None
        brand_text, generic, be = brand_hint, generic_hint, 0
    rest = text[be:]
    attrs = {"generic": generic, "brand": brand_text}
    sm = STRENGTH_RE.search(rest)
    if sm and sm.start() < 40:
        unit = sm.group(2)
        unit = "µg" if unit.lower() == "mcg" else unit
        attrs["dose"] = "%s %s" % (sm.group(1), unit)
    rm = ROUTE_RE.search(rest)
    if rm:
        attrs["route"] = rm.group(1).lower()
    fm = FORM_RE.search(rest)
    if fm:
        attrs["form"] = FORM_EN.get(fm.group(1).lower(), fm.group(1))
    sched = None
    m4 = SCHED4_RE.search(rest)
    md = SCHED_DASH_RE.search(rest)
    if m4:
        cols = list(m4.groups())
        attrs["schedule_mo_mi_ab_na"] = " ".join(cols)
        sched = "-".join(cols[:3]) if cols[3] == "0" else "-".join(cols)
    elif md:
        cols = [c for c in md.groups() if c is not None]
        sched = "-".join(cols)
    if sched:
        attrs["schedule"] = sched
    wm = WEEKLY_RE.search(rest)
    if wm:
        attrs["frequency"] = "%sx/week" % wm.group(1)
    dm = DAILY_RE.search(rest)
    if dm:
        attrs["frequency"] = "%sx/day" % dm.group(1)
    pm = PUFFS_RE.search(text)
    if pm:
        attrs["amount"] = "%s puffs" % (pm.group(1) or pm.group(2))
    for rx, en in TIME_WORDS:
        if rx.search(rest):
            attrs["timing"] = en
            break
    # leftover numbers between strength and route that we could not interpret (e.g. "0,5")
    if sm and rm and sm.end() < rm.start():
        left = rest[sm.end():rm.start()].strip()
        if re.fullmatch(r"\d+(?:[.,]\d+)?", left):
            attrs["unparsed"] = left
    attrs["category"] = GENERIC_CATEGORY.get(generic)
    return attrs


def med_label(attrs):
    g = attrs.get("generic") or "medication"
    parts = [g[:1].upper() + g[1:]]
    if attrs.get("brand") and attrs["brand"].lower() != g.lower():
        parts[0] += " (%s)" % attrs["brand"]
    if attrs.get("amount"):
        parts.append(attrs["amount"])
    if attrs.get("dose"):
        parts.append(attrs["dose"])
    if attrs.get("form") and attrs["form"] not in ("unit(s)", "dose(s)", "tablet"):
        parts.append(attrs["form"])
    if attrs.get("route") and attrs["route"] != "oral":
        parts.append(attrs["route"])
    if attrs.get("schedule"):
        parts.append(attrs["schedule"])
    if attrs.get("frequency"):
        parts.append(attrs["frequency"])
    if attrs.get("timing"):
        parts.append(attrs["timing"])
    return " ".join(parts)
