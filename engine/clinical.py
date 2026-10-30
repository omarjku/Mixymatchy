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

  0. Overrides both: a non-clinical self-description anywhere in the text (the requester's own identity, not a
     third party they mention: 'I'm the GP and her daughter asked me' stays clinical) ('I am a nurse and her neighbour',
     'I'm a doctor (I actually deliver pizza)', 'Ärztin, eigentlich Journalistin') -> not authorised.  A
     first-person cue (I am / I'm / ich bin / je suis / soy / sono / ben / أنا ...) followed by the non-clinical
     term with only filler or role words in between, or 'actually / really / eigentlich / en fait ...' right
     beside the term in a first-person request.  Mentioning someone else ('her husband called') does not count.

Not authorised = zero patient facts on screen.  This is a demo safeguard: real deployments authorise by
the logged-in user's role, never by what someone types.
"""
import json
import os
import re

from .understand import fold, norm_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.environ.get("SECOND_LOOK_CLINICAL_ROLES", os.path.join(ROOT, "rulebook", "clinical_roles.json"))
L = r"\w"          # Unicode letters/digits (accent-folded text, Arabic script included)
PREFIX_MIN = 6
PREFIX_MIN_INTL = 8
ARABIC = re.compile(r"[\u0600-\u06FF]")
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")

NOT_AUTHORISED_MESSAGE = ("Second Look shows patient information only to clinical staff for a care task. "
                          "Please state your clinical role and what you are doing, e.g. 'Anaesthetist, pre-op check'.")
NOT_AUTHORISED_SUGGESTIONS = [
    "Anaesthetist, pre-op check before breast surgery",
    "GP, diabetes review",
    "Ward nurse, admission handover",
    "Pharmacist, medication review",
]

# no requester at all but a clear clinical request ('STAT CT head, any bleeding risk meds?'): still no data
# (an explicit requester is required), but the message asks for the role and offers the request with one
NEEDS_ROLE_MESSAGE = ("Please say who you are (your clinical role) and the task. Second Look shows patient "
                      "information only to clinical staff for a care task, e.g. 'Emergency physician, head CT: "
                      "bleeding risk medication?' or 'Ward nurse, admission handover'.")
ROLE_EXAMPLES = ["Emergency physician", "GP", "Ward nurse"]

_LEX = None


def _term_rx(term, mode):
    """mode 'en': whole word (+ plural s/es); 'de' / 'intl': also a word prefix from PREFIX_MIN(_INTL)
    characters (German compounds, Romance / Turkish inflections); Arabic script: whole word with the
    article / conjunction prefixes and common suffixes."""
    t = re.escape(fold(norm_text(term).strip()))
    pre = "(?<![%s])" % L
    if ARABIC.search(term):
        return re.compile(pre + "(?:[وفبلك])?(?:ال|لل)?" + t + "(?:ة|ه|ها|ي|ات|ون|ين)?(?![%s])" % L)
    if CJK.search(term):  # Chinese / Japanese: no spaces between words, plain substring
        return re.compile(t)
    if (mode == "de" and len(term) >= PREFIX_MIN) or (mode == "intl" and len(term) >= PREFIX_MIN_INTL):
        return re.compile(pre + t + "[%s-]*" % L)          # prefix: the span covers the whole word
    return re.compile(pre + t + "(?:s|es)?(?![%s])" % L)


def lexicon():
    global _LEX
    if _LEX is None:
        with open(PATH, encoding="utf-8") as fh:
            d = json.load(fh)
        pats = d.get("patterns") or {}

        def terms(kind):
            return [(t, _term_rx(t, mode)) for mode in ("en", "de", "intl")
                    for t in d.get("%s_%s" % (kind, mode)) or []]
        tit = d.get("titles_override") or {}
        pol = d.get("policy") or {}
        pur = d.get("non_clinical_purpose") or {}
        _LEX = {
            "clinical": terms("clinical"),
            "non_clinical": terms("non_clinical"),
            "titles": [(t, _term_rx(t, "en")) for t in tit.get("words") or []],
            "title_exceptions": {fold(norm_text(x)) for x in tit.get("exceptions") or []},
            "policy": [(t, _term_rx(t, "intl" if len(t) >= PREFIX_MIN_INTL else "en")) for t in pol.get("refuse_roles") or []],
            "purpose": [(t, re.compile(r"(?<![\w'])%s(?![\w])" % re.escape(fold(norm_text(t)))))
                        for t in pur.get("phrases") or []],
            "clin_words": sorted({fold(norm_text(x)) for k_ in ("clinical_en", "clinical_de") for x in d.get(k_) or []
                                  if " " not in x and len(x) >= 5}),
            "non_words": sorted({fold(norm_text(x)) for k_ in ("non_clinical_en", "non_clinical_de")
                                 for x in d.get(k_) or [] if " " not in x and len(x) >= 5}),
            "patterns": [re.compile(fold(p)) for p in pats.get("clinical") or []],
            "exclude": [re.compile(fold(p)) for p in pats.get("exclude") or []],
        }
    return _LEX


def _hits(t, entries):
    return [(m.start(), m.end(), term) for term, rx in entries for m in rx.finditer(t)]


def _pattern_hits(t, lex):
    out = []
    for m in re.finditer(r"[^\W\d_]+", t):
        w = m.group(0)
        if any(x.search(w) for x in lex["exclude"]):
            continue
        if any(p.search(w) for p in lex["patterns"]):
            out.append((m.start(), m.end(), w))
    return out


def excluded_word(w):
    """Words the lexicon marks as not a clinical person (astrologist, Tierarzt, ...)."""
    return any(x.search(fold(w)) for x in lexicon()["exclude"])


def is_clinical_word(w):
    """A single word that is an explicit lexicon term (used to stop fuzzy matching, e.g. urologist -> neurologist)."""
    lex = lexicon()
    w = fold(norm_text(w).strip())
    return any(rx.fullmatch(w) for _t, rx in lex["clinical"]) or \
        (not excluded_word(w) and any(p.search(w) for p in lex["patterns"]))


# ----------------------------------------------------------------- self-description (any position)
_SELF = re.compile(r"(?<![\w'])(i am|i'm|i work as|i work for|i work at|i actually|i really|my job is|"
                   r"my profession is|by profession|ich bin|bin ich|ich arbeite als|ich arbeite bei|ich arbeite fur|"
                   r"beruflich|je suis|je travaille comme|je travaille pour|soy|trabajo como|trabajo para|sono|"
                   r"lavoro come|lavoro per|ben|benim|انا|"
                   r"i (?:actually |really |just |only )?(?:deliver|drive|work|write|sell|run|own|teach)s?|"
                   r"ich (?:liefere|fahre|arbeite|schreibe|verkaufe)|"
                   r"[^\W\d_][\w&-]* here|hier)(?![\w'])")   # 'doctor here, well really ...'
_REPORTED = re.compile(r"\s*(?:has |hat |had )?(?:just |already |gerade |schon )?([^\W_][\w'-]*)(?:\s+(an|angerufen))?")
# a term followed by one of these starts a clause about someone else ('her daughter asked me', 'her husband
# wants to know'): the requester mentions a third party, it is not how they describe themselves
_THIRD_PARTY_VERB = set("""asked asks ask wants want wanted would called calls rang phoned phones says said told tells
is was has had wonders wondered needs needed requested mentioned worries worried brought came comes visited
fragt fragte möchte mochte will wollte hat hatte rief ruft ist war sagt sagte meint bittet bat
demande demandait veut a pregunta pregunto quiere chiede vuole soruyor soruyordu istiyor
phoned phone rang rings ringing calling called emailed wrote writes texted messaged contacted came asking
wanting wonder wondering worried concerned visited visiting dropped left reported reports
angerufen anrief anruft fragte gefragt erkundigt erkundigte meldete gemeldet schrieb
appele appelle telephone a appele llamo llamó llama ha llamado ha chiamato chiama ha telefonato aradi sordu""".split())


def third_party_mention(t, s, e):
    """A non-clinical term followed by a reporting verb ('the husband called', 'her son phoned the practice',
    'die Tochter hat angerufen'): someone else is mentioned as the source of the question."""
    m = _REPORTED.match(t[e:])
    return bool(m and (m.group(1) in _THIRD_PARTY_VERB or m.group(2)))
_REALLY = re.compile(r"(?<![\w'])(actually|really|in fact|in reality|honestly|eigentlich|tatsachlich|"
                     r"in wirklichkeit|en fait|en realite|en realidad|in realta|aslinda|في الحقيقة)(?![\w'])")
_POSS_BEFORE = re.compile(r"(?<![\w'])(?:her|his|their|the patient's|patient's|ihr|ihre|ihrem|ihren|ihrer|sein|seine|"
                          r"seinem|seinen|sa|son|ses|su|sus|sua|suo)\s+$")
_POSSESSIVE = {"just", "only", "simply", "nur", "the", "her", "his", "their", "patient's", "patients", "patient", "ihr", "ihre", "ihrer", "sein",
               "seine", "der", "die", "des", "sa", "son", "su", "sua"}
# words that may stand between the cue and the non-clinical term ('I am a nurse and her neighbour')
_GAP_OK = set("""a an the her his their its my also too as well and or but just only now currently actually really
in fact for at with from by deliver delivers drive drives write writes work works sell sells run runs own
ein eine einer einem einen der die das ihr ihre ihrer sein seine auch und oder nur eigentlich tatsachlich
beim bei fur als von un une le la les sa son et aussi en el los las su y tambien il lo gli sua e anche bir ve
de da ayrica""".split())
_ARTICLES = {"a", "an", "the", "ein", "eine", "un", "une", "una", "uno", "bir"}


def _gap_ok(t, a, b, clin_spans, allowed):
    """Every token of t[a:b] is an allowed filler word or lies inside a clinical / role span; no clause break."""
    if re.search(r"[,;.:!?()]", t[a:b]):
        return False
    for m in re.finditer(r"[^\W_][\w'-]*", t[a:b]):
        s0, e0 = a + m.start(), a + m.end()
        if m.group(0) in allowed or any(cs <= s0 and e0 <= ce for cs, ce in clin_spans):
            continue
        return False
    return True


def self_described_non_clinical(t, non_hits, clin_spans):
    """-> the non-clinical term the requester uses about themselves, or None (t: folded, normalised text)."""
    selfs = list(_SELF.finditer(t))
    if not selfs:
        return None
    reallys = list(_REALLY.finditer(t))
    for s, e, term, _k in non_hits:
        if third_party_mention(t, s, e):  # 'her daughter asked me about ...'
            continue
        for m in selfs:  # 'I am (a nurse and) her neighbour'
            if m.end() <= s and s - m.end() <= 80 and _gap_ok(t, m.end(), s, clin_spans, _GAP_OK):
                return term
        for m in reallys:  # 'eigentlich Journalistin', 'a journalist really' (first-person request only)
            if (m.end() <= s and _gap_ok(t, m.end(), s, (), _ARTICLES | _POSSESSIVE) or
                    m.start() >= e and _gap_ok(t, e, m.start(), (), set())):
                return term
    return None


_SELF_JOB = re.compile(r"(?<![\w'])i (?:actually |really |just |only |mostly )?(?:deliver|drive|sell|clean|cook|"
                       r"guard|fix|repair)s?(?![\w'])")


def fuzzy_non_clinical(word):
    """A typo of a non-clinical word ('Cleanr', 'jounalist'), unless the word is closer to a clinical one."""
    import difflib
    w = fold(norm_text(word))
    lex = lexicon()
    if w in lex["clin_words"] or w in lex["non_words"]:
        return None
    best_non = max(((difflib.SequenceMatcher(None, w, x).ratio(), x) for x in lex["non_words"]
                    if abs(len(x) - len(w)) <= 2 and x[:1] == w[:1]), default=(0, None))
    best_cl = max((difflib.SequenceMatcher(None, w, x).ratio() for x in lex["clin_words"]
                   if abs(len(x) - len(w)) <= 2), default=0)
    return best_non[1] if best_non[0] >= 0.85 and best_non[0] > best_cl else None


def _label(term):
    return term[:1].upper() + term[1:]


def classify(text, kb_alias=None, task_evidence=False, kb_role=False):
    """-> {"decision": "kb_role" | "clinical_term" | "clinical_task" | "not_clinical" | "no_role",
           "clinical": bool, "term": str|None, "label": str|None}"""
    t = fold(norm_text(text or ""))
    lex = lexicon()
    clin = [(s, e, term, "clinical_term") for s, e, term in _hits(t, lex["clinical"]) + _pattern_hits(t, lex)]
    if kb_alias:
        clin += [(m.start(), m.end(), kb_alias, "kb_role")
                 for m in re.compile("(?<![%s])%s" % (L, re.escape(fold(norm_text(kb_alias))))).finditer(t)]
    for term, rx in lex["purpose"]:  # a non-clinical purpose refuses whoever asks ('just curious', 'for court')
        if rx.search(t):
            return {"decision": "not_clinical", "clinical": False, "term": term, "label": None}
    # owner policy (clinical_roles.json 'policy'): clinical-adjacent roles that do not treat are refused
    pol = _hits(t, lex["policy"])
    clin = [h for h in clin if not any(ps <= h[0] and h[1] <= pe for ps, pe, _t in pol)]
    non = [(s, e, term, "not_clinical") for s, e, term in _hits(t, lex["non_clinical"])
           if not any(cs <= s and e <= ce and (ce - cs) > (e - s) for cs, ce, _t, _k in clin)]
    non += [(s, e, term, "not_clinical") for s, e, term in pol]
    # title words win even inside a clinical-looking term (ward manager, medical director, health inspector)
    for s, e, term in _hits(t, lex["titles"]):
        inside = [t[cs:ce].strip() for cs, ce, _t, _k in clin if cs <= s and e <= ce]
        if not any(x in lex["title_exceptions"] for x in inside):
            non.append((s, e, term, "not_clinical"))
            clin = [h for h in clin if not (h[0] <= s and e <= h[1])]
    # typos of non-clinical words in the leading phrase ('Cleanr') are checked before any fuzzy clinical match
    lead0 = re.search(r"[,;:.!?()]|\s[-–]\s", t)
    lead0 = lead0.start() if lead0 else len(t)
    lead_clin = any(cs < lead0 for cs, _ce, _t, _k in clin)  # 'Medico di guardia': a clinical word is there
    for m in ([] if lead_clin else re.finditer(r"[^\W\d_][\w-]{4,}", t[:lead0])):
        if any(cs <= m.start() < ce for cs, ce, _t, _k in clin + non):
            continue
        term = fuzzy_non_clinical(m.group(0))
        if term:
            non.append((m.start(), m.end(), term, "not_clinical"))
    # relational identity: 'doctor's wife', 'GP's assistant', 'pharmacist's cousin' -> not that role
    for cs, ce, _t, _k in clin:
        rel = re.match(r"(?:'s|s'|’s)\s+", t[ce:])
        if rel and any(s == ce + rel.end() for s, _e, _t2, _k2 in non):
            return {"decision": "not_clinical", "clinical": False, "term": t[cs:ce] + "'s", "label": None}
    # a first-person non-clinical job ('I drive the ambulance only', 'I deliver pizza'): no clinical role in it
    for m in _SELF_JOB.finditer(t):
        end = re.search(r"[,;:.!?()]", t[m.end():])
        clause = (m.end(), m.end() + (end.start() if end else len(t)))
        if not any(clause[0] <= cs < clause[1] for cs, _ce, _t, _k in clin):
            return {"decision": "not_clinical", "clinical": False, "term": m.group(0).strip(), "label": None}
    if clin or kb_role:  # a clinical requester who mentions a relative as the source of the question
        non = [h for h in non if not third_party_mention(t, h[0], h[1])]
    selfd = self_described_non_clinical(t, non, [(cs, ce) for cs, ce, _t, _k in clin])
    if selfd:  # a non-clinical self-description overrides any clinical claim, wherever it stands
        return {"decision": "not_clinical", "clinical": False, "term": selfd, "label": None}
    # deny wins in the leading role phrase ('Hospital director, ...', 'Porter here, rapid response ...'): a
    # non-clinical identity there refuses, whatever clinical words follow; 'her daughter' (possessive) is a mention
    lead = re.search(r"[,;:.!?()]|\s[-–]\s", t)
    lead_end = lead.start() if lead else len(t)
    for s, e, term, _k in non:
        if s < lead_end and not _POSS_BEFORE.search(t[:s]):
            return {"decision": "not_clinical", "clinical": False, "term": term, "label": None}
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
