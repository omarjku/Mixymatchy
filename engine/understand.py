"""Understand: free situation text -> role, tasks, modifiers.

Deterministic keyword/synonym matcher (default).  An optional LLM proposal
(engine/llm.py) is accepted only for IDs that exist in the rulebook.
"""
import difflib
import functools
import re

from . import llm
from .data import rulebook

DEFAULT_AS_OF = "2016-04-15"

_MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
           "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
           "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9,
           "sept": 9, "oct": 10, "nov": 11, "dec": 12,
           "januar": 1, "februar": 2, "märz": 3, "mai": 5, "juni": 6, "juli": 7, "oktober": 10,
           "dezember": 12}
_SEASONS = {"spring": "03", "summer": "06", "autumn": "09", "fall": "09", "winter": "12"}

_PROCEDURES = ["quadrantectomy", "mastectomy", "lumpectomy", "breast-conserving surgery",
               "intraoperative radiotherapy", "iort", "radiotherapy", "sentinel", "biopsy",
               "ct angiography", "cta", "ct", "mri", "angiography", "endarterectomy", "stent",
               "duplex", "ultrasound", "echocardiography", "colonoscopy", "gastroscopy",
               "cholecystectomy", "surgery", "operation", "chemotherapy", "endocrine therapy"]
_DRUG_WORDS = ["contrast", "iodinated contrast", "aspirin", "heparin", "insulin", "metformin",
               "tamoxifen", "letrozole", "anastrozole", "exemestane", "warfarin", "clopidogrel",
               "steroid", "cortisone", "antibiotic", "opioid", "nsaid", "ibuprofen", "propofol"]


# Accents of French / Spanish / Italian / Turkish are folded (médecin -> medecin, kardiyoloğ -> kardiyolog) so
# that requests typed with or without them match the same lexicon entries; German umlauts and ß are kept
# (the German lexicon is written with them).  Arabic: diacritics dropped, alef / ya variants unified.
_FOLD = str.maketrans({
    "é": "e", "è": "e", "ê": "e", "ë": "e", "á": "a", "à": "a", "â": "a", "ã": "a", "í": "i", "ì": "i", "î": "i",
    "ï": "i", "ó": "o", "ò": "o", "ô": "o", "õ": "o", "ú": "u", "ù": "u", "û": "u", "ñ": "n", "ç": "c", "ş": "s",
    "ğ": "g", "ı": "i", "œ": "oe", "æ": "ae", "\u0307": None,
    "أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ـ": None,
    **{chr(c): None for c in range(0x064B, 0x0653)},
})


_UMLAUT = str.maketrans({"ä": "a", "ö": "o", "ü": "u"})


def fold(s):
    """Matching form of normalised text: German / Turkish umlauts folded too (ä->a, ö->o, ü->u; 1:1, so
    positions stay valid).  Lexicon terms and request text are both folded before matching, so 'Prämedikation',
    'pramedikation', 'ameliyat öncesi' and 'ameliyat oncesi' all match."""
    return (s or "").translate(_UMLAUT)


def norm_text(text):
    t = (text or "").lower().replace("’", "'").translate(_FOLD)
    t = re.sub(r"[‐‑‒–—]", "-", t)
    return re.sub(r"\s+", " ", t)


@functools.lru_cache(maxsize=None)
def _phrase_rx(phrase, whole_word):
    """Compiled once per (phrase, whole_word): thousands of lexicon phrases overflow re's own 512-entry cache, so
    every request re-compiled them (~1 s per request on the Render free CPU, DECISIONS 24 v3.2)."""
    p = re.escape(phrase.lower())
    pre = r"(?<![\w])" if phrase[:1].isalnum() else ""
    post = r"(?![\w])" if whole_word and phrase[-1:].isalnum() else ""
    return re.compile(pre + p + post)


def _you_are_spans(t):
    """Character spans of 'you are (the) X' / 'I am (the) X' clauses."""
    spans = []
    for m in re.finditer(r"\b(you are|you're|i am|i'm|as (?:the|her|a|an))\b", t):
        end = len(t)
        stop = re.search(r"[.;:!?]|\b(and|who|planning|reviewing|checking|assessing|on|in|at)\b",
                         t[m.end():])
        if stop:
            end = m.end() + stop.start()
        spans.append((m.end(), min(end, m.end() + 60)))
    return spans


def match_role(t, roles):
    spans = _you_are_spans(t)
    best = None
    for idx, role in enumerate(roles):
        for syn in role.get("synonyms") or []:
            for m in _phrase_rx(syn, True).finditer(t):
                score = len(syn) + (100 if any(a <= m.start() < b for a, b in spans) else 0)
                key = (score, -idx)
                if best is None or key > best[0]:
                    best = (key, role["id"], syn, "synonym")
    if best:
        return best[1], best[2], best[3]
    # nearest-role fallback: fuzzy match of words / bigrams against synonyms (typos, variants)
    words = re.findall(r"[a-zäöüß&-]+", t)
    grams = words + [" ".join(words[i:i + 2]) for i in range(len(words) - 1)]
    best = None
    for role in roles:
        for syn in role.get("synonyms") or []:
            if len(syn) < 5:
                continue
            for g in grams:
                r = difflib.SequenceMatcher(None, g, syn).ratio()
                if r >= 0.82 and (best is None or r > best[0]):
                    best = (r, role["id"], syn)
    if best:
        return best[1], best[2], "fuzzy"
    # specialty stems ("...ologist", "...ology") without a rulebook role -> other
    return "other", None, "fallback"


def match_tasks(t, tasks):
    hits = {}
    for task in tasks:
        found = []
        first = None
        for trig in task.get("triggers") or []:
            m = _phrase_rx(trig, False).search(t)
            if m:
                found.append(trig)
                first = m.start() if first is None else min(first, m.start())
        if found:
            hits[task["id"]] = (len(found), first, found)
    return hits


def extract_modifiers(t):
    mods = {"drugs": [], "procedures": [], "side": None, "dates": [], "times": [], "body_sites": []}
    for d in _DRUG_WORDS:
        if _phrase_rx(d, True).search(t):
            mods["drugs"].append(d)
    for p in _PROCEDURES:
        if _phrase_rx(p, True).search(t) and not any(p in q for q in mods["procedures"]):
            mods["procedures"].append(p)
    left = re.search(r"\b(left|links|linke[nrs]?)\b", t)
    right = re.search(r"\b(right|rechts|rechte[nrs]?)\b", t)
    mods["side"] = "left" if left and not right else "right" if right and not left else (
        "both" if left and right else None)
    for site in ("breast", "eye", "carotid", "neck", "head", "heart", "kidney", "prostate", "bone"):
        if re.search(r"\b%s" % site, t):
            mods["body_sites"].append(site)
    for d, mo, y in re.findall(r"\b(\d{1,2})\.?\s+([a-zä]+)\s+(\d{4})\b", t):
        if mo in _MONTHS:
            mods["dates"].append("%s-%02d-%02d" % (y, _MONTHS[mo], int(d)))
    for d, mo, y in re.findall(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b", t):
        mods["dates"].append("%s-%02d-%02d" % (y, int(mo), int(d)))
    mods["dates"] += re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", t)
    for mo, y in re.findall(r"\b([a-zä]+)\s+(\d{4})\b", t):
        if mo in _MONTHS and not any(x.startswith("%s-%02d" % (y, _MONTHS[mo])) for x in mods["dates"]):
            mods["dates"].append("%s-%02d" % (y, _MONTHS[mo]))
        elif mo in _SEASONS:
            mods["dates"].append("%s-%s" % (y, _SEASONS[mo]))
    mods["times"] = re.findall(r"\b(\d{1,2}:\d{2})\b", t)
    return mods


def understand(text, as_of=None, use_llm=True):
    roles_rb, tasks_rb = rulebook()
    roles = roles_rb.get("roles", [])
    tasks = tasks_rb.get("tasks", [])
    role_by_id = {r["id"]: r for r in roles}
    task_by_id = {t["id"]: t for t in tasks}
    t = norm_text(text)

    role_id, role_hit, role_method = match_role(t, roles)
    hits = match_tasks(t, tasks)
    method = "rules"

    proposal = llm.understand(text, list(role_by_id), list(task_by_id)) if use_llm else None
    if proposal:
        rid = proposal.get("role_id")
        tids = [x for x in proposal.get("task_ids") or [] if x in task_by_id]
        if rid in role_by_id and (role_method != "synonym" or rid == role_id):
            role_id, role_method = rid, "llm"
        for tid in tids:
            hits.setdefault(tid, (1, len(t), ["llm"]))
        method = "rules+llm"

    role = role_by_id.get(role_id) or role_by_id.get("other") or {"id": "other"}
    suppressed = set(role.get("suppress_tasks") or [])
    for tid in hits:
        suppressed |= set(task_by_id[tid].get("suppress_tasks") or [])
    triggered = sorted((tid for tid in hits if tid not in suppressed),
                       key=lambda tid: (hits[tid][1], -hits[tid][0]))
    task_ids = triggered or [x for x in role.get("default_tasks") or [] if x in task_by_id]
    if not task_ids:
        task_ids = ["general_overview"]

    mods = extract_modifiers(t)
    as_of_date = as_of or DEFAULT_AS_OF
    m = re.search(r"\bas of (\d{4}-\d{2}-\d{2})\b", t)
    if m and not as_of:
        as_of_date = m.group(1)
    return {
        "text": text,
        "role_id": role["id"],
        "role_label": role.get("label_en", role["id"]),
        "role_match": {"method": role_method, "matched": role_hit},
        "task_ids": task_ids,
        "task_labels": [task_by_id[x].get("label_en", x) for x in task_ids],
        "task_match": {tid: hits[tid][2] for tid in task_ids if tid in hits},
        "tasks_from": "triggers" if triggered else "role_default",
        "modifiers": mods,
        "as_of_date": as_of_date,
        "method": method,
    }
