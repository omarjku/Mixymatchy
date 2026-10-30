"""Clinical gate: patient data only for a clinical requester (rulebook/clinical_roles.json, hand-written).

Decision, deterministic, after KB routing (engine/route.py):
  1. A role word in the text that the KB recognises, or a clinical term from the lexicon (incl. generic
     -ologist / -iatrist / -therapist / -arzt patterns), or an explicit non-clinical requester
     (firefighter, journalist, neighbour, relative, ...): the FIRST such word in the text decides.
     A non-clinical term inside a clinical one ('student' in 'medical student', 'family' in 'family
     doctor') does not count.
  2. No role word at all: a clear clinical task (a KB bundle matched with a multi-word / hyphenated /
     10+ character tag, or two or more tags, e.g. 'pre-op check before breast surgery'), or a named
     sex-specific examination (rulebook/applicability.json), implies a clinical context -> clinical.
     Anything else ('tell me everything about her', empty text) -> not authorised.

Not authorised = zero patient facts on screen.  This is a demo safeguard: real deployments authorise by
the logged-in user's role, never by what someone types.
"""
import json
import os
import re

from .understand import norm_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.environ.get("SECOND_LOOK_CLINICAL_ROLES", os.path.join(ROOT, "rulebook", "clinical_roles.json"))
L = r"a-z0-9äöüß"
PREFIX_MIN = 6

NOT_AUTHORISED_MESSAGE = ("Second Look shows patient information only to clinical staff for a care task. "
                          "Please state your clinical role and what you are doing, e.g. 'Anaesthetist, pre-op check'.")
NOT_AUTHORISED_SUGGESTIONS = [
    "Anaesthetist, pre-op check before breast surgery",
    "GP, diabetes review",
    "Ward nurse, admission handover",
    "Pharmacist, medication review",
]

_LEX = None


def _term_rx(term, german):
    t = re.escape(norm_text(term).strip())
    pre = "(?<![%s])" % L
    if german and len(term) >= PREFIX_MIN:
        return re.compile(pre + t + "[%s-]*" % L)          # prefix: the span covers the whole word
    return re.compile(pre + t + "(?:s|es)?(?![%s])" % L)


def lexicon():
    global _LEX
    if _LEX is None:
        with open(PATH, encoding="utf-8") as fh:
            d = json.load(fh)
        pats = d.get("patterns") or {}
        _LEX = {
            "clinical": [(t, _term_rx(t, False)) for t in d.get("clinical_en") or []]
                        + [(t, _term_rx(t, True)) for t in d.get("clinical_de") or []],
            "non_clinical": [(t, _term_rx(t, False)) for t in d.get("non_clinical_en") or []]
                            + [(t, _term_rx(t, True)) for t in d.get("non_clinical_de") or []],
            "patterns": [re.compile(p) for p in pats.get("clinical") or []],
            "exclude": [re.compile(p) for p in pats.get("exclude") or []],
        }
    return _LEX


def _hits(t, entries):
    return [(m.start(), m.end(), term) for term, rx in entries for m in rx.finditer(t)]


def _pattern_hits(t, lex):
    out = []
    for m in re.finditer(r"[a-zäöüß]+", t):
        w = m.group(0)
        if any(x.search(w) for x in lex["exclude"]):
            continue
        if any(p.search(w) for p in lex["patterns"]):
            out.append((m.start(), m.end(), w))
    return out


def excluded_word(w):
    """Words the lexicon marks as not a clinical person (astrologist, Tierarzt, ...)."""
    return any(x.search(w) for x in lexicon()["exclude"])


def is_clinical_word(w):
    """A single word that is an explicit lexicon term (used to stop fuzzy matching, e.g. urologist -> neurologist)."""
    lex = lexicon()
    w = norm_text(w).strip()
    return any(rx.fullmatch(w) for _t, rx in lex["clinical"]) or \
        (not excluded_word(w) and any(p.search(w) for p in lex["patterns"]))


def _label(term):
    return term[:1].upper() + term[1:]


def classify(text, kb_alias=None, task_evidence=False, kb_role=False):
    """-> {"decision": "kb_role" | "clinical_term" | "clinical_task" | "not_clinical" | "no_role",
           "clinical": bool, "term": str|None, "label": str|None}"""
    t = norm_text(text or "")
    lex = lexicon()
    clin = [(s, e, term, "clinical_term") for s, e, term in _hits(t, lex["clinical"]) + _pattern_hits(t, lex)]
    if kb_alias:
        clin += [(m.start(), m.end(), kb_alias, "kb_role")
                 for m in re.compile("(?<![%s])%s" % (L, re.escape(norm_text(kb_alias)))).finditer(t)]
    non = [(s, e, term, "not_clinical") for s, e, term in _hits(t, lex["non_clinical"])
           if not any(cs <= s and e <= ce and (ce - cs) > (e - s) for cs, ce, _t, _k in clin)]
    # ties at one position: the longer span wins; equal spans: non-clinical wins (conservative)
    rank = {"not_clinical": 0, "kb_role": 1, "clinical_term": 2}
    allw = sorted(clin + non, key=lambda h: (h[0], -(h[1] - h[0]), rank[h[3]]))
    if allw:
        s, e, term, kind = allw[0]
        if kind == "kb_role":
            return {"decision": "kb_role", "clinical": True, "term": term, "label": None}
        if kind == "clinical_term":
            return {"decision": "clinical_term", "clinical": True, "term": term, "label": _label(t[s:e].strip())}
        return {"decision": "not_clinical", "clinical": False, "term": term, "label": None}
    if kb_role:  # role proposed by the optional LLM (no alias in the text) and no other role word
        return {"decision": "kb_role", "clinical": True, "term": None, "label": None}
    if task_evidence:
        return {"decision": "clinical_task", "clinical": True, "term": None, "label": None}
    return {"decision": "no_role", "clinical": False, "term": None, "label": None}


def strong_task(bundles_matched, fallback_bundle=None):
    """A KB bundle matched clearly enough to imply a clinical task without a stated role."""
    for bid, v in (bundles_matched or {}).items():
        if bid == fallback_bundle:
            continue
        score, tags = (v["score"], v["tags"]) if isinstance(v, dict) else v
        if score >= 2 or any(" " in x or "-" in x or len(x) >= 10 for x in tags):
            return True
    return False
