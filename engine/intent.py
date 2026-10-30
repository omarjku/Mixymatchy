"""'No task, no data' (docs/DECISIONS.md 19): patient data only for a recognisable clinical TASK.

Runs after the clinical gate (engine/clinical.py) in engine/screen.build_screen_kb.  A clinical requester
whose request, once every role word is removed, contains

  * no KB task (bundle tag match on the role-free text),
  * no named topic (rulebook/kb_overlay.json topics) and no applicability item,
  * and no clinical content word (KB tag words, slot labels, task_terms, topic terms, drug names, the record's
    concept labels, and the intent words of rulebook/task_intent.json: assess, worry, before surgery, coming in,
    abklären, Aufnahme ...)

gets the 'needs_task' screen: zero patient facts, a short message asking for role + task, and examples.
Greetings, filler, test words and keyboard mash never count ('never' list).  Deterministic; the optional
LLM can only restrict further (engine/screen.py), never turn needs_task into data.
"""
import json
import os
import re

from .understand import fold, norm_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.environ.get("SECOND_LOOK_TASK_INTENT", os.path.join(ROOT, "rulebook", "task_intent.json"))
PREFIX_MIN = 6
WORD = re.compile(r"[^\W\d_][\w'-]*")

NEEDS_TASK_MESSAGE = ("Please describe your task. Second Look shows patient information only for a clinical task: "
                      "state your role and what you are doing, e.g. 'Anaesthetist, pre-op check'.")
NEEDS_TASK_SUGGESTIONS = [  # generic examples, nothing taken from the open record
    "Anaesthetist, pre-op check",
    "Ward nurse, admission handover",
    "Pharmacist, medication review",
    "GP, annual check-up",
]

_LEX = None
_VOCAB = {}


def lexicon():
    global _LEX
    if _LEX is None:
        with open(PATH, encoding="utf-8") as fh:
            d = json.load(fh)
        f = lambda xs: [fold(norm_text(x).strip()) for x in xs or []]  # noqa: E731
        intent = [x for k_ in ("intent_en", "intent_de", "intent_intl", "body_symptom_en", "body_symptom_de",
                               "body_symptom_intl") for x in f(d.get(k_))]
        _LEX = {"intent": intent, "never": set(f(d.get("never"))), "tag_stop": set(f(d.get("tag_stop")))}
    return _LEX


def _words(s):
    return WORD.findall(fold(norm_text(s or "")))


def vocabulary(kb, store=None):
    """-> (single words, phrases): the clinical content vocabulary (cached per KB / store)."""
    key = (id(kb), id(store))
    if key in _VOCAB:
        return _VOCAB[key]
    from .kb import bundle_tags
    lex = lexicon()
    words, phrases = set(), set()
    for x in lex["intent"]:
        (phrases if " " in x else words).add(x)
    for b in kb.bundles:
        for t in bundle_tags(b):
            if t.startswith("("):
                continue
            words.update(w for w in _words(t) if len(w) >= 5 and w not in lex["tag_stop"])
    for s in kb.slots:
        words.update(w for w in _words(s.get("label")) if len(w) >= 5)
    ov = getattr(kb, "overlay", None) or {}
    for g in (ov.get("task_terms") or {}).get("groups") or []:
        words.update(fold(norm_text(x)) for x in g)
    for tp in ov.get("topics") or []:
        for xs in (tp.get("terms") or {}).values():
            for x in xs:
                x = fold(norm_text(x).strip())
                (phrases if " " in x else words).add(x)
    try:
        with open(os.path.join(ROOT, "rulebook", "drugs.json"), encoding="utf-8") as fh:
            drugs = json.load(fh)
        for brand, v in drugs.items():
            if brand.startswith("_") or not isinstance(v, dict):
                continue
            words.update(w for w in _words(brand) + _words(v.get("generic")) if len(w) >= 4)
    except (OSError, ValueError):
        pass
    if store is not None:
        from .focus import concepts
        for label in concepts(store)[0]:
            words.update(w for w in _words(label) if len(w) >= 5)
    words -= lex["never"]
    _VOCAB[key] = (frozenset(words), tuple(sorted(phrases)))
    return _VOCAB[key]


def _intent_sets():
    lex = lexicon()
    return ({x for x in lex["intent"] if " " not in x} - lex["never"], {x for x in lex["intent"] if " " in x})


STEM_SUFFIXES = ("ing", "ed", "es", "s", "en", "er", "e")
COMPOUND_MIN = 7   # a vocabulary word of 7+ characters inside a longer word (German compounds: Eignungsuntersuchung)


def _known(w, words, longs):
    if w in words:
        return True
    for suf in STEM_SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            b = w[:-len(suf)]
            if b in words or b + "e" in words or (len(b) >= 4 and b[-1] == b[-2] and b[:-1] in words):
                return True
    return len(w) > PREFIX_MIN and any(w.startswith(x) or (len(x) >= COMPOUND_MIN and x in w) for x in longs)


def role_free(text, aliases=()):
    """The request with the requester's words blanked: the KB role alias the router matched, clinical lexicon
    terms and -ologist patterns (engine/clinical.py), 'I am' / 'ich bin'.  Other roles' names stay: 'triage'
    or 'imaging' can be the task.  What is left is what the person asks for."""
    from . import clinical as C
    from .understand import _phrase_rx
    t = fold(norm_text(text or ""))
    out = list(t)

    def blank(s, e):
        out[s:e] = " " * (e - s)
    for a in aliases or ():
        a = fold(norm_text(a or "").strip())
        if a:
            for m in _phrase_rx(a, True).finditer(t):
                blank(m.start(), m.end())
    lex = C.lexicon()
    words, phrases = _intent_sets()
    for s, e, _t in C._hits(t, lex["clinical"]) + C._pattern_hits(t, lex):
        span = t[s:e].strip()
        if span in words or span in phrases:  # a service word that is itself the task ('ward round', 'consult')
            continue
        blank(s, e)
    for s, e in [(m.start(), m.end()) for m in re.finditer(
            r"(?<![\w])(?:i am|i'm|im|i work as|ich bin|as (?:the|a|an)|als)(?![\w])", t)]:
        blank(s, e)
    return "".join(out)


def clinical_words(text, kb, store=None):
    """Clinical content words / phrases in text (already role-free), in order of appearance."""
    words, phrases = vocabulary(kb, store)
    t = fold(norm_text(text or ""))
    hits = []
    for p in phrases:
        m = re.search(r"(?<![\w])%s(?![\w])" % re.escape(p), t)
        if m:
            hits.append((m.start(), p))
    longs = [w for w in words if len(w) >= PREFIX_MIN]
    for m in WORD.finditer(t):
        w = m.group(0).strip("'-")
        if not w or w in lexicon()["never"]:
            continue
        if _known(w, words, longs):
            hits.append((m.start(), w))
    return [w for _s, w in sorted(hits)]


def has_task(text, kb, store=None, aliases=(), named_topics=(), applicability_items=()):
    """-> {"actionable": bool, "reason": str, "rest": role-free text, "words": [...]}.  aliases: the role
    alias(es) the router matched in text."""
    from .route import match_bundles
    rest = role_free(text, aliases)
    if named_topics:
        return {"actionable": True, "reason": "named topic", "rest": rest, "words": []}
    if applicability_items:
        return {"actionable": True, "reason": "applicability item", "rest": rest, "words": []}
    if not WORD.search(rest):
        return {"actionable": False, "reason": "no task stated (role only, empty or symbols)", "rest": rest, "words": []}
    from .screen import OVERVIEW_RX, REVIEW_RX
    if REVIEW_RX.search(rest) or OVERVIEW_RX.search(rest):
        return {"actionable": True, "reason": "review / overview request", "rest": rest, "words": []}
    matched = {b: v for b, v in match_bundles(rest, kb).items() if b != kb.fallback_bundle}
    if matched:
        return {"actionable": True, "reason": "KB task", "rest": rest, "words": sorted(matched)}
    cw = clinical_words(rest, kb, store)
    if cw:
        return {"actionable": True, "reason": "clinical content word", "rest": rest, "words": cw}
    return {"actionable": False, "reason": "no clinical task in the request", "rest": rest, "words": []}
