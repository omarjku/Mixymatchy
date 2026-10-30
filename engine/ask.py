"""Specific questions: the routing guide's fallback layer 3 ('ad-hoc search').

A request that asks about one thing ('does she have a pacemaker?', 'did she ever have a fall?', 'Blutgruppe?')
gets an answer card for that thing: the facts or passages that mention it, quoted word for word with their
source, or an explicit 'Nothing found' naming the documents and the words searched.  Never a guess: the card
holds only extracted facts and verbatim passages, and the search words come from rulebook/ask_lexicon.json
(English -> German), so a subject with no German entry says so instead of claiming the record is silent.

Subjects a named topic (rulebook/kb_overlay.json 'topics') or a matched bundle tag already covers are left to
those; this layer only fills the gaps.
"""
import json
import os
import re
from functools import lru_cache

from .data import RULEBOOK_DIR
from .fill import fmt_date, group_items
from .understand import fold, norm_text

MAX_ITEMS = 6        # facts or passages quoted per answer card
MAX_SUBJECTS = 3     # answer cards per request
WHOLE_WORD_BELOW = 5  # search words shorter than this match whole words only ('CT', 'PET', 'OP')
ADMIN_CATEGORIES = {"case_number", "encounter", "date_of_birth", "age"}  # never an answer to a clinical question

# a question: a question mark, or an interrogative opening a clause (English / German)
QUESTION_RX = re.compile(
    r"\?|(?:^|[,:;.]\s*|\b(?:and|und)\s+)(?:does|did|do|has|had|have|is|was|were|are|any|what|which|when|"
    r"how|can|could|tell me|show me|check whether|check if|hat|hatte|ist|war|gibt es|gab es|wann|welche[rsn]?|"
    r"wie|liegt)\b")

# the subject follows these openings; the first pattern that matches wins
_WHO = r"(?:she|he|they|the patient|patient|pt|the pt|sie|er|die patientin|der patient|pat\.?)"
SUBJECT_PATTERNS = [re.compile(p) for p in (
    r"\b(?:does|did|has|had|have|is|was)\s+%s\s+(?:ever\s+|already\s+|currently\s+|still\s+|previously\s+|recently\s+)?"
    r"(?:have|had|has|got|get|take|taken|takes|use|used|uses|been on|been|on|taking|using|receive[ds]?|received|"
    r"undergo(?:ne)?|suffer(?:ed|s)? from|experience[ds]?|carry|carries|need|needs|wear|wears)?\s*(.+)" % _WHO,
    r"\b(?:what|which|how)\s+(?:is|was|are|were|'s)\s+(?:her|his|their|the patient'?s?|the)\s+(.+)",
    r"\bwhat'?s\s+(?:her|his|their|the patient'?s?|the)\s+(.+)",
    r"\bhow\s+(\w+)\s+(?:is|was|are)\s+%s\b" % _WHO,  # 'how tall is she?', 'how heavy is she?'
    r"\bhow\s+(?:much|many|often)\s+(?:does|did|do)\s+%s\s+(\w+)" % _WHO,  # 'how much does she weigh / drink?'
    r"\bwhen\s+(?:was|were|did)\s+(?:her|his|their|the|she|he)\s+(?:last\s+)?(.+)",
    r"\b(?:any|history of|hx of|known|evidence of|signs? of|record of|mention of|documented)\s+(.+)",
    r"\b(?:hat|hatte)\s+(?:sie|er|die patientin|der patient)\s+(?:je|jemals|schon|bereits|aktuell)?\s*(.+)",
    r"\b(?:gibt es|gab es|liegt)\s+(.+)",
    r"\b(?:was ist|wie ist|wie hoch ist|welche[rsn]?)\s+(?:ihr|ihre|sein|seine|der|die|das)?\s*(.+)",
)]

_CUT = re.compile(r"[?!.;:()\[\]]")
_SPLIT = re.compile(r",|/|\s*[+&]\s*|\s+(?:and|or|und|oder|plus)\s+")
_LEAD = re.compile(r"^(?:a|an|any|the|some|known|her|his|their|its|ever|eine?[nmrs]?|ein|kein[e]?|ihre?|seine?|der|die|das|"
                   r"of|for|on|about|to|with|history of|signs of|evidence of|been)\s+")
_TRAIL = re.compile(r"\s+(?:ever|a lot|lots|often|much|anymore|lately|before|already|currently|now|at all|in the past|documented|recorded|noted|mentioned|"
                    r"known|so far|last|recently|today|previously|in the record|in the letters|dose|doses|dosage|"
                    r"status|values?|levels?|results?|findings?|score|list|history|hx|"
                    r"je|jemals|bisher|schon|bekannt|dokumentiert|vor|gehabt|bekommen|genommen)$")
STOP = set("""a an the and or of for to in on at with about from by is are was were be been being do does did
has had have she he her his they their it its patient pt any some there this that these those what which when
how who whom whose why where ever please me my i we you your can could would should will may might must
documented recorded noted mentioned status history known current currently previous previously last recent
before after still yet also only just all much many more most other such same so than too very
check checking review show tell list give find look need needs want wants
summary overview everything anything something info information details detail relevant important
problem problems issue issues finding findings result results note notes record records letter letters data
done missing new changed change changes happened going wrong ok okay fine normal old dose doses dosage
sie er ihr ihre sein seine der die das ein eine einen kein keine und oder ist war hat hatte gibt es gab
je jemals bisher schon bekannt dokumentiert patientin patient bitte wie was wann welche welcher welches wo""".split())


def is_question(task_text):
    return bool(QUESTION_RX.search(norm_text(task_text or "")))


def _clean(phrase):
    p = re.sub(r"\s+", " ", phrase or "").strip(" -'\"")
    for _ in range(3):
        p = _LEAD.sub("", p).strip()
        p = _TRAIL.sub("", p).strip()
    words = [w for w in re.findall(r"[\w'+-]+", p)]
    while words and words[-1] in STOP:  # 'ultrasound done' -> 'ultrasound'
        words.pop()
    while words and words[0] in STOP:
        words.pop(0)
    if not words or all(w in STOP for w in words) or len(words) > 4:
        return None
    return " ".join(words)


def subjects(task_text):
    """Subjects a question asks about, in order ('pacemaker', 'blood type', 'fall'); all of them (the screen
    answers at most MAX_SUBJECTS after dropping those a topic covers, and names the rest)."""
    t = norm_text(task_text or "")
    out = []
    for clause in re.split(r"[?;]|\.\s", t):
        tails = [m.group(1) for m in (rx.search(clause) for rx in SUBJECT_PATTERNS) if m][:1]
        if not tails and "?" in t:  # a bare subject: 'Blutgruppe?', 'pacemaker?' (a short phrase, not a sentence
            bare = clause.split(":")[-1].split(",")[-1]  # in another language: 'jakie leki ... przyjmuje?')
            tails = [bare] if len(bare.split()) <= 3 else []
        for tail in tails:
            for part in _SPLIT.split(_CUT.split(tail)[0]):
                s = _clean(part)
                # only Latin script: the letters are German, a Cyrillic / CJK phrase cannot be searched in them
                if s and s not in out and not NON_LATIN.search(s):
                    out.append(s)
    return out


NON_LATIN = re.compile(r"[^\W\d_a-zA-Z\u00c0-\u024f]")


def _wordlike(w):
    """A real word, not keyboard mash ('asdfgh', 'qwertz'): Latin words need vowels and no long consonant run."""
    if NON_LATIN.search(w):
        return len(w) >= 2
    v = sum(c in "aeiouyäöü" for c in w)
    return (len(w) >= 4 and v / len(w) >= 0.25 and len(set(w)) > 2
            and not re.search(r"[^aeiouyäöü\W\d]{5,}", w))


def content_words(task_text, never=()):
    """Words of a question that could name a clinical subject (not stop words, filler or keyboard mash)."""
    words = re.findall(r"[^\W\d_][\w'-]*", fold(norm_text(task_text or "")))
    return [w for w in words if w not in STOP and w not in never and _wordlike(w)]


# medical word endings (English / Latin / German): an unknown subject with one of them is a clinical question
MEDICAL_WORD = re.compile(r"(?:itis|osis|oses|ose|oma|omas|emia|aemia|ämie|pathy|pathie|algia|algie|ectomy|ektomie|"
                          r"otomy|otomie|ostomy|scopy|skopie|graphy|graphie|gram|iasis|plasia|plasie|trophy|trophie|"
                          r"penia|penie|cele|uria|urie|ism|ismus|insufficiency|insuffizienz|stenosis|stenose|"
                          r"thrombosis|embolism|embolie|infarction|infarkt|syndrome|syndrom|disease|disorder|"
                          r"deficiency|mangel|fracture|fraktur|cancer|karzinom|carcinoma|tumou?r|lesion|läsion|"
                          r"infection|infektion|allergy|allergie|virus|viral|bacterial|vaccine|impfung|"
                          r"tablet|dose|dosis|level|wert|pain|schmerz|ache)$")


def clinical_subject(store, task_text, never=()):
    """A content word of the question that is medical by its form ('sarcoidosis', 'gout'?) or that the letters
    contain ('Raucherin') -> the word, else None ('what's the weather like?' is not a clinical question)."""
    words = content_words(task_text, never)
    for w in words:  # other scripts: only the task vocabulary (engine/intent.py) can tell, not the word's form
        if not NON_LATIN.search(w) and MEDICAL_WORD.search(w):
            return w
    text = store_text(store)
    return next((w for w in words if len(w) >= 5 and _word_rx(w).search(text)), None)


_STORE_TEXT = {}


def store_text(store):
    """All passage text of the store, folded and lowercased (cached per store)."""
    if id(store) not in _STORE_TEXT:
        _STORE_TEXT.clear()
        _STORE_TEXT[id(store)] = fold(" ".join(p.get("text") or "" for p in store.passages).lower())
    return _STORE_TEXT[id(store)]


@lru_cache(maxsize=1)
def lexicon():
    with open(os.path.join(RULEBOOK_DIR, "ask_lexicon.json"), encoding="utf-8") as fh:
        terms = json.load(fh).get("terms") or {}
    out = {}
    for k, v in terms.items():
        v = v if isinstance(v, dict) else {"words": v}
        out[fold(norm_text(k))] = {"words": list(v.get("words") or []), "slot": v.get("slot"),
                                   "label": re.compile(v["label"], re.I) if v.get("label") else None,
                                   "sections": list(v.get("sections") or [])}
    return out


def _phrase_in(phrase, text):
    # a hyphen joins words: 'work' is not in 'work-up'
    return re.search(r"(?<![\w-])%s(?:s|es)?(?![\w-])" % re.escape(phrase), text) is not None


FUZZY_CUTOFF = 0.85  # a typo in a single-word lexicon key ('pacemakr', 'stroids')


def _entries(subject):
    """Lexicon entries the subject names (longest first), whose German search words it uses, or (typos) whose
    single-word key one of its words nearly spells."""
    import difflib
    s = fold(subject)
    hits = [k for k in sorted(lexicon(), key=len, reverse=True) if _phrase_in(k, s)]
    if not hits:  # a German subject: the entries that list it among their search words
        hits = [k for k, e in lexicon().items()
                if any(_word_rx(w).search(s) for w in e["words"] if len(w) >= WHOLE_WORD_BELOW)]
    if not hits:
        keys = [k for k in lexicon() if " " not in k and len(k) >= WHOLE_WORD_BELOW]
        for w in re.findall(r"[\w]{5,}", s):
            hits += [k for k in difflib.get_close_matches(w, keys, n=1, cutoff=FUZZY_CUTOFF) if k not in hits]
    return [lexicon()[k] for k in hits]


def slot_for(subject, kb):
    """The KB slot that answers this subject (lexicon 'slot'), if any: the routing guide's layer 2 comes before
    a word search."""
    return next((e["slot"] for e in _entries(subject) if e["slot"] and e["slot"] in kb.slot_by_id), None)


def search_words(subject):
    """-> (words, from_lexicon).  The German words of the lexicon entries the subject names; otherwise the
    subject's own significant words, which in German letters may miss a mention under another word."""
    words = []
    for e in _entries(subject):
        for w in e["words"]:
            if w not in words:
                words.append(w)
    if words:
        return words, True
    own = [w for w in re.findall(r"[\w-]+", subject) if w not in STOP and len(w) >= 3]
    if len(own) > 1:
        own = [subject] + own
    return own, False


def _word_rx(word):
    w = fold(word.lower())
    post = r"(?![\w])" if len(w) < WHOLE_WORD_BELOW else ""
    return re.compile(r"(?<![\w])" + re.escape(w) + post)


def covered(subject, kb, named_topics, bundle_tags):
    """A named topic or a matched bundle tag already answers this subject."""
    from .focus import match_topics
    s = fold(subject)
    if match_topics(s, getattr(kb, "overlay", None) or {}):
        return True
    return any(fold(norm_text(t)) in s for t in bundle_tags if len(t) > 3)


def answer_card(store, subject, as_of=None):
    """One card for one asked subject: matching facts (translated, with sources), else the passages that
    mention it word for word, else 'Nothing found' naming what was searched."""
    words, from_lexicon = search_words(subject)
    rxs = [_word_rx(w) for w in words]
    # only letters written by the as-of date
    docs = [d for d in store.docs if as_of is None or str(store.doc_date(d) or "")[:10] <= str(as_of)[:10]]
    known = set(docs)
    hit_passages = [p for p in store.passages if p["doc_id"] in known
                    and any(r.search(fold((p.get("text") or "").lower())) for r in rxs)]
    labels = [e["label"] for e in _entries(subject) if e["label"]]
    # 'was an ultrasound done?': only procedures and plans answer it, not a diagnosis whose sentence mentions it
    sections = {x for e in _entries(subject) for x in e["sections"]}

    def english(f):  # the English label without bracketed original terms ('Case (Fall) number' is no fall)
        return fold(re.sub(r"\([^)]*\)", "", str(f.get("label_en") or "")).lower())

    # a fact answers when its own quote holds a search word (not merely its passage), or its English label
    # matches the entry's label pattern; the subject's own English word only without German search words
    facts = [f for f in store.facts
             if f.get("category") not in ADMIN_CATEGORIES and set(store.fact_docs(f)) & known
             and (not sections or f.get("ips_section") in sections)
             and (as_of is None or str(f.get("date") or "") <= str(as_of) or not f.get("date"))
             and (any(r.search(fold(str(f.get("quote") or "").lower())) for r in rxs)
                  or any(rx.search(english(f)) for rx in labels)
                  or (not from_lexicon and _phrase_in(fold(subject), english(f))))]
    label = "Your question: %s" % subject
    why = "You asked about %s; every passage of the %d documents was searched for it." % (subject, len(docs))
    searched = {"documents": len(docs), "passages_scanned": len(store.passages), "terms": words,
                "from_lexicon": from_lexicon}
    base = {"need": "ask_%s" % re.sub(r"\W+", "_", subject).strip("_"), "slot": None, "label_en": label,
            "priority": "P1", "why": why, "sources": [], "rules": [], "origins": ["your question"],
            "group": "question", "searched": searched, "collapsed": 0}
    if facts:
        items = group_items(store, facts)
        items.sort(key=lambda it: str(it.get("date") or ""), reverse=True)
        items = items[:MAX_ITEMS]
        return dict(base, shape="list", compute="question", status="consistent", items=items,
                    facts=[x for it in items for x in it["facts"]],
                    passages=list(dict.fromkeys(p for it in items for p in it["passages"])),
                    value_en=" | ".join("%s (%s)" % (it["label_en"], fmt_date(it["date"], it.get("date_precision")))
                                        for it in items))
    if hit_passages:
        hit_passages.sort(key=lambda p: (str(store.doc_date(p["doc_id"]) or ""), p["id"]), reverse=True)
        shown = hit_passages[:MAX_ITEMS]
        lines = [{"label": "Letter of %s" % fmt_date(store.doc_date(p["doc_id"])),
                  "value": re.sub(r"\s+", " ", p.get("text") or "").strip(), "passages": [p["id"]],
                  "formula": "verbatim passage containing a search word (%s); no fact was extracted from it"
                             % ", ".join(words)} for p in shown]
        more = len(hit_passages) - len(shown)
        return dict(base, shape="list", compute="question", status="consistent", items=[], facts=[],
                    passages=[p["id"] for p in shown], computed_lines=lines,
                    note=("%d more passage(s) mention it." % more) if more else None,
                    value_en="Mentioned in %d passage(s), quoted word for word below; read them in context."
                             % len(hit_passages))
    if from_lexicon:
        value = ("Nothing found for %s: none of the %d documents contains any of these words: %s."
                 % (subject, len(docs), ", ".join(words)))
    else:
        value = ("Nothing found for '%s': none of the %d documents contains %s. The letters are in German and no "
                 "German search word is stored for this term, so check the letters if it matters."
                 % (subject, len(docs), ", ".join("'%s'" % w for w in words) or "'%s'" % subject))
    return dict(base, shape="record_check", compute="record_check", status="not_documented", items=[], facts=[],
                passages=[], date=None, value_en=value)

