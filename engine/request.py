"""Request semantics: what the free text says besides role and task (rules, no API key needed).

  * exclusions   'not interested in X', 'ohne X', 'sans X', 'X hariç', 'X is not relevant' ...: the
                 span names topics (engine/focus.py lexicon) whose facts are suppressed on the screen.
                 The safety core (allergies, age/sex) is never suppressed.
  * instructions text that tries to steer the tool ('ignore previous instructions', 'add diagnosis X',
                 'print all documents', 'you are now ...'): blanked before routing, so it can never add
                 content, choose a role or authorise; listed in the routing note.
  * other patient a request that names a different patient (another name, ID, date of birth or age than
                 the open record): refused with the reason; nothing of this record is shown.

Cue words are generic (EN/DE/FR/ES/IT/TR/AR, accent-folded like engine/understand.norm_text); no
patient content.  Clinical-language review: source TODO-cite.
"""
import datetime
import os
import re

from .understand import norm_text

# ----------------------------------------------------------------- exclusions
_PRE_CUES = [
    r"not interested in", r"no interest in", r"not (?:looking|asking) (?:for|about)", r"no need (?:for|to see)",
    r"(?:i )?(?:don't|do not|dont) (?:need|want|care about|show|include)", r"(?:please )?(?:don't|do not) show",
    r"without", r"except(?: for)?", r"excluding", r"exclude", r"apart from", r"other than", r"leave out",
    r"skip", r"but not", r"never mind", r"not the",
    r"ohne", r"außer", r"ausser", r"(?:bin )?nicht interessiert an", r"kein interesse an", r"ausgenommen",
    r"abgesehen von", r"bitte nicht", r"nicht nach", r"keine angaben zu",
    r"sans", r"sauf", r"excepte", r"hormis", r"pas interesse(?:e)? par", r"je ne veux pas",
    r"sin", r"excepto", r"salvo", r"no me interesa(?:n)?", r"no interesa(?:n)?", r"no quiero",
    r"senza", r"tranne", r"eccetto", r"non mi interessa(?:no)?", r"non interessa(?:no)?", r"non voglio",
    r"بدون", r"ما عدا", r"باستثناء", r"غير مهتم ب", r"لا اريد", r"دون",
]
_POST_CUES = [
    r"(?:is|are) not (?:relevant|needed|required|of interest|important)", r"(?:is|are) irrelevant",
    r"not relevant", r"not needed", r"not of interest",
    r"(?:ist|sind) nicht relevant", r"nicht relevant", r"nicht nötig", r"nicht notwendig", r"uninteressant",
    r"(?:n'est|ne sont) pas (?:pertinent|necessaire|utile)s?",
    r"no (?:es|son) relevantes?", r"no (?:es|son) necesari[oa]s?",
    r"non (?:e|sono) rilevant[ei]", r"non serv(?:e|ono)",
    r"haric", r"disinda", r"olmadan", r"gerek yok", r"onemli degil", r"istemiyorum", r"ilgilenmiyorum",
    r"غير مهم", r"غير ضروري",
]
_W = r"[\w'/-]+"
_STOP_AFTER = r"(?=[.;:!?,]|\b(?:but|focus|please|aber|bitte|mais|pero|ma|ama|ve|and then|instead|statt|sondern|stattdessen)\b|$)"
PRE_RX = re.compile(r"(?<![\w])(?:%s)(?![\w])\s*((?:%s\s*){1,6}?)%s" % ("|".join(_PRE_CUES), _W, _STOP_AFTER))
POST_RX = re.compile(r"((?:%s\s+){1,5}?)(?:%s)(?![\w])" % (_W, "|".join(_POST_CUES)))
_POST_START = re.compile(r"[.;:!?,]\s*")


def exclusion_spans(t):
    """-> [(start, end)] of normalised text t that a negation cue excludes (cue included)."""
    spans = [(m.start(), m.end()) for m in PRE_RX.finditer(t)]
    for m in POST_RX.finditer(t):
        s = m.start(1)
        # the excluded phrase starts after the last punctuation before the cue
        seg = t[:m.end(1)]
        cut = max((x.end() for x in _POST_START.finditer(seg)), default=0)
        spans.append((max(s, cut), m.end()))
    return _merge(spans)


# ----------------------------------------------------------------- instructions inside the request
_INSTR = [
    r"(?:ignore|disregard|forget|override|bypass)\b[^.;!?]{0,40}?\b(?:instructions?|rules?|prompts?|guidelines?|restrictions?|filters?|settings?)\b[^.;!?]*",
    r"\b(?:you are now|you're now|act as|pretend(?: to be)?|from now on you|new instructions?|system prompt|developer mode|admin mode|jailbreak)\b[^.;!?]*",
    r"\b(?:add|insert|record|write|enter|create|append|document|put|set|change|update|delete|remove|edit|modify|correct|replace|mark)\b[^.;!?]{0,30}?\b(?:diagnos\w*|allerg\w*|medication\w*|drugs?|entr(?:y|ies)|notes?|facts?|records?|values?|findings?|results?|field)\b[^.;!?]*",
    r"\b(?:print|export|send|e-?mail|download|dump|output|copy|forward|share|upload|show|list|give(?: me)?|display)\b[^.;!?]{0,15}?\b(?:all|every|everything|the (?:whole|entire|complete|full)|complete|full|entire)\b[^.;!?]{0,25}?\b(?:documents?|records?|letters?|files?|data|chart|notes|information|reports?|history|everything)\b[^.;!?]*",
    r"\b(?:ignoriere|vergiss|missachte)\b[^.;!?]*",
    r"\b(?:füge|fuge|trage|ergänze|erganze|lösche|losche|ändere|andere|schreibe|setze)\b[^.;!?]{0,40}?\b(?:diagnose\w*|allergie\w*|medikament\w*|eintrag\w*|befund\w*|wert\w*|hinzu|ein)\b[^.;!?]*",
    r"\b(?:drucke|exportiere|sende|schicke|zeige|gib)\b[^.;!?]{0,15}?\b(?:alle|sämtliche|samtliche|die gesamte|das gesamte|komplett\w*)\b[^.;!?]*",
    r"\b(?:ignore[zr]?|oublie[zr]?)\b[^.;!?]{0,30}?\binstructions?\b[^.;!?]*",
    r"\b(?:ajoute[zr]?|supprime[zr]?|modifie[zr]?|ecri[st]?|ecrire)\b[^.;!?]{0,30}?\b(?:diagnostic|allergie|traitement|medicament)s?\b[^.;!?]*",
    r"\b(?:imprime[zr]?|exporte[zr]?|envoie[zr]?|montre[zr]?)\b[^.;!?]{0,15}?\btou[st]\b[^.;!?]*",
    r"\b(?:ignora|ignore|olvida|olvide)\b[^.;!?]{0,30}?\b(?:instrucciones|istruzioni|reglas|regole)\b[^.;!?]*",
    r"\b(?:anade|agrega|anadir|agregar|borra|elimina|aggiungi|cancella|modifica|scrivi)\b[^.;!?]{0,30}?\b(?:diagnostico|diagnosi|alergia|allergia|medicamento|farmaco)s?\b[^.;!?]*",
    r"\b(?:imprime|exporta|envia|stampa|esporta|invia|mostra)\b[^.;!?]{0,15}?\b(?:todos|todas|tutti|tutte|todo|tutto)\b[^.;!?]*",
    r"\b(?:talimatlari|kurallari)\b[^.;!?]{0,20}?\b(?:yok say|unut|gormezden gel)\w*[^.;!?]*",
    r"\b(?:teshis|tani|alerji|ilac)\w*\s+(?:ekle|sil|degistir|yaz)\w*[^.;!?]*",
    r"\b(?:tum|butun)\s+(?:belgeleri|kayitlari|dosyalari|raporlari)\b[^.;!?]*",
    r"(?:تجاهل|انس)[^.;!?،]*(?:التعليمات|القواعد)[^.;!?]*",
    r"(?:اضف|اضافة|احذف|عدل|غير)\s+(?:تشخيص|حساسية|دواء)[^.;!?]*",
    r"(?:اطبع|ارسل|صدر)\s+(?:جميع|كل)[^.;!?]*",
]
INSTR_RX = [re.compile(p) for p in _INSTR]


def instruction_spans(t):
    return _merge([(m.start(), m.end()) for r in INSTR_RX for m in r.finditer(t)])


def _merge(spans):
    out = []
    for s, e in sorted(spans):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def blank(t, spans):
    for s, e in spans:
        t = t[:s] + " " * (e - s) + t[e:]
    return t


# ----------------------------------------------------------------- other patient
_TITLES = (r"Mr|Mrs|Ms|Miss|Mister|Herr|Herrn|Frau|Hr|Fr|Madame|Mme|Monsieur|Mlle|Mademoiselle|"
           r"Señora|Senora|Sra|Señor|Senor|Sr|Signora|Sig\.ra|Signor|Sig|Bay|Bayan")
NAME = r"[A-ZÄÖÜÉÈÁÍÓÚÑÇŞ][a-zäöüßéèáíóúñçşğı'-]+"
TITLE_RX = re.compile(r"(?<![\w])(?:%s)\.?\s+(?!(?:Dr|Doktor|Doctor|Prof|Professor|Dott|Docteur)\b)(%s(?:\s+%s)?)" % (_TITLES, NAME, NAME))
SELF_RX = re.compile(r"(?i)(?:i am|i'm|my name is|this is|ich bin|mein name ist|hier ist|je suis|je m'appelle|soy|me llamo|sono|mi chiamo|benim adim|ben)\s*$")
NAMED_RX = re.compile(r"(?:\b(?:named|called|name is|name:|namens|heißt|heisst|s'appelle|se llama|si chiama|adli|isimli)\s+)(%s(?:\s+%s)?)" % (NAME, NAME))
PATIENT_NAME_RX = re.compile(r"\b(?:patient|paciente|patiente|paziente|Patientin|Patient)\s+(%s)\s+(%s)\b" % (NAME, NAME))
AR_TITLE_RX = re.compile(r"(?:السيد|السيدة|المريض|المريضة)\s+([^\s،,.;:!?]+)")
AR_NOT_NAME = {"المريضة", "المريض", "nn", "التي", "الذي", "هذه", "هذا", "عمرها", "عمره"}
ID_RX = re.compile(r"(?i)(?<![\w])(?:patient(?:in)?|pat\.?|id|mrn|pid|case|fall(?:nummer|zahl|nr)?\.?|aufnahmezahl|"
                   r"svnr|versicherungsnummer|dossier|expediente|cartella|hasta no)"
                   r"\s*(?:id|no\.?|nr\.?|number|nummer|numero|#)?\s*[:#]?\s*((?:[a-z]{1,4}[-_])?\d[\d\-_/.]{3,}\d)")
NN_RX = re.compile(r"\bNN_\d{4}-\d{4}\b")
DOB_RX = re.compile(r"(?i)(?:born(?: on)?|dob|date of birth|geb(?:oren)?\.?(?: am)?|geburtsdatum|ne[e]? le|nacid[oa] el|nato il|nata il|dogum tarihi)\s*:?\s*(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})|(?:born(?: in)?|geboren|geb\.|jahrgang|nee? en|nacid[oa] en|nat[oa] nel)\s+(\d{4})")
AGE_RX = re.compile(r"(?i)(?<![\d.])(\d{1,3})\s*(?:-|\s)?(?:year|yr)s?[- ]old|(?<![\d.])(\d{1,3})\s*-?\s*j(?:ä|a)hrige?[rnms]?\b|\baged? (\d{1,3})\b"
                    r"|(?<![\d.])(\d{1,3}) ans\b|(?<![\d.])(\d{1,3}) anos\b|(?<![\d.])(\d{1,3}) anni\b|(?<![\d.])(\d{1,3}) yasinda")
ANOTHER_RX = re.compile(r"(?i)\b(?:another|different|other|second|next) patient\b|\b(?:anderen?|andere[rn]?|zweite[rn]?|nächsten?) patient(?:in|en)?\b"
                        r"|\b(?:autre|deuxieme) patiente?\b|\b(?:otro|otra) paciente\b|\b(?:altro|altra) paziente\b|\bbaska (?:bir )?hasta\b"
                        r"|مريض(?:ة)? (?:اخر|اخرى)")

_IDENT = {}


def identity(store):
    """Names, identifiers, date of birth and the plausible age range of the open record (cached)."""
    key = id(store)
    if key in _IDENT:
        return _IDENT[key]
    from .data import RAW_DIR, _load
    pj = _load(os.path.join(RAW_DIR, "patient.json"), {}) or {}
    names = {w.lower() for w in re.findall(r"[^\W\d_]+", str(pj.get("name") or "")) if len(w) > 1}
    ids = {re.sub(r"\D", "", str(pj.get("id") or ""))}
    nn = set()
    for p in store.passages:
        nn |= set(NN_RX.findall(p.get("text") or ""))
    ids |= {re.sub(r"\D", "", x) for x in nn}
    ids |= {re.sub(r"\D", "", str(d)) for d in store.docs}
    for f in store.facts:
        if f.get("category") == "case_number":
            ids.add(re.sub(r"\D", "", str((f.get("attrs") or {}).get("value") or "")))
    adm = pj.get("latestAdmission")
    if isinstance(adm, dict) and adm.get("id"):
        ids.add(re.sub(r"\D", "", str(adm["id"])))
    ids.discard("")
    for p in store.passages:  # names the letters themselves use for her (address block, 'Frau X')
        for m in TITLE_RX.finditer(p.get("text") or ""):
            names |= {w.lower() for w in re.findall(r"[^\W\d_]+", m.group(1)) if len(w) > 1}
    dob = None
    for f in store.facts:
        if f.get("category") == "date_of_birth":
            m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", str((f.get("attrs") or {}).get("value") or ""))
            if m:
                dob = datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
                break
    if dob is None and pj.get("dateOfBirth"):
        try:
            dob = datetime.date.fromisoformat(str(pj["dateOfBirth"])[:10])
        except ValueError:
            dob = None
    ages = None
    if dob:
        dates = [str(d.get("date") if isinstance(d, dict) else "")[:10] for d in store.docs.values()] \
            if isinstance(store.docs, dict) else []
        first = min([x for x in dates if re.match(r"\d{4}-\d{2}-\d{2}", x)] or [str(datetime.date.today())])
        a0 = _age(dob, datetime.date.fromisoformat(first))
        ages = (a0 - 1, _age(dob, datetime.date.today()) + 1)
    _IDENT[key] = {"names": names, "ids": ids, "nn": nn, "dob": dob, "ages": ages}
    return _IDENT[key]


def _age(dob, at):
    return at.year - dob.year - ((at.month, at.day) < (dob.month, dob.day))


def other_patient(text, store):
    """-> reason (str) when the request names a different patient than the open record, else None."""
    if not text:
        return None
    ident = identity(store)
    t = norm_text(text)
    if ANOTHER_RX.search(text) or ANOTHER_RX.search(t):
        return "The request is about another patient."
    for m in NN_RX.finditer(text):
        if m.group(0) not in ident["nn"]:
            return "The request names patient %s; the open record is a different patient." % m.group(0)
    for m in ID_RX.finditer(t):
        digits = re.sub(r"\D", "", m.group(1))
        if len(digits) >= 6 and not re.match(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}$", m.group(1)) \
                and digits not in ident["ids"] and not any(digits in x or x in digits for x in ident["ids"] if len(x) >= 4):
            return "The request names identifier %s, which does not belong to the open record." % m.group(1)
    for rx in (TITLE_RX, NAMED_RX, PATIENT_NAME_RX):
        for m in rx.finditer(text):
            if rx is TITLE_RX and SELF_RX.search(text[:m.start()]):
                continue  # the requester introducing themselves
            words = [w.lower() for w in re.findall(r"[^\W\d_]+", m.group(1) if rx is not PATIENT_NAME_RX
                                                   else m.group(1) + " " + m.group(2))]
            if words and words[0] in ("nn",):
                continue
            if _common_words(words):  # 'Sr. Nurse', 'Patient Diabetes Review': vocabulary, not a name
                continue
            if not any(w in ident["names"] for w in words):
                return "The request names %s; the open record belongs to a different patient." % m.group(0).strip()
    for m in AR_TITLE_RX.finditer(t):
        w = m.group(1)
        if w not in AR_NOT_NAME and w not in ident["names"] and not w.startswith("nn"):
            return "The request names %s; the open record belongs to a different patient." % m.group(0)
    if ident["dob"]:
        for m in DOB_RX.finditer(t):
            if m.group(4):
                if int(m.group(4)) != ident["dob"].year:
                    return "The request gives a different year of birth (%s)." % m.group(4)
                continue
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            y = y + 1900 if y < 100 and y > 30 else y + 2000 if y < 100 else y
            if (d, mo, y) != (ident["dob"].day, ident["dob"].month, ident["dob"].year):
                return "The request gives a different date of birth (%s)." % m.group(0).strip()
    if ident["ages"]:
        lo, hi = ident["ages"]
        for m in AGE_RX.finditer(t):
            a = next(int(x) for x in m.groups() if x)
            if not lo <= a <= hi:
                return "The request describes a %d-year-old; the open record's patient is %d-%d years old." % (
                    a, lo + 1, hi - 1)
    return None


_VOCAB = None


def _common_words(words):
    """Words that are vocabulary (KB tags/aliases, topic terms), not names ('Patient Diabetes Review')."""
    global _VOCAB
    if _VOCAB is None:
        from .kb import bundle_tags, kb, role_aliases
        k = kb()
        voc = set()
        for b in k.bundles:
            for x in bundle_tags(b):
                voc |= set(norm_text(x).split())
        for r in k.roles:
            for x in role_aliases(r):
                voc |= set(norm_text(x).split())
        for tp in (getattr(k, "overlay", None) or {}).get("topics") or []:
            for xs in (tp.get("terms") or {}).values():
                for x in xs:
                    voc |= set(norm_text(x).split())
        voc |= {"review", "overview", "summary", "check", "admission", "discharge", "handover", "planning",
                "aufnahme", "entlassung", "kontrolle", "nachsorge", "visite", "konsil", "übergabe"}
        _VOCAB = voc
    return any(w in _VOCAB for w in words)


# ----------------------------------------------------------------- self-correction of the role
CORRECTION_RX = re.compile(
    r"(?<![\w])(?:wait|no wait|actually|sorry|i mean|correction|scratch that|"
    r"eigentlich|ich meine|nein|korrektur|besser gesagt|pardon|je veux dire|plutot|en fait|perdon|quiero decir|"
    r"o sea|mejor dicho|anzi|cioe|volevo dire|yani|aslinda|pardon)(?![\w])")
_POSS = re.compile(r"(?:her|his|their|the patient's|ihr|ihre|ihrem|ihren|sein|seine|son|sa|su|sua)\s+$")


_ALIAS_RX = {}
_FIRST_PERSON = re.compile(r"(?<![\w'])(?:i am|i'm|i work as|ich bin|ich arbeite als|je suis|soy|sono|ben|انا)"
                           r"(?:\s+(?:a|an|the|her|his|ein|eine|der|die|un|une|una|uno|il|la|el|bir))?\s+$")


def _role_spans(t, kb):
    from . import clinical as C
    from .kb import role_aliases
    from .understand import _phrase_rx, fold
    ft = fold(t)
    key = id(kb)
    if key not in _ALIAS_RX:
        _ALIAS_RX[key] = [_phrase_rx(a, True) for a in {fold(norm_text(a).strip()) for r in kb.roles
                                                         for a in role_aliases(r)} if len(a) >= 2]
    spans = [(m.start(), m.end()) for rx_ in _ALIAS_RX[key] for m in rx_.finditer(ft)]
    lex = C.lexicon()
    spans += [(s0, e0) for s0, e0, _t in C._hits(ft, lex["clinical"]) + C._pattern_hits(ft, lex)]
    # non-clinical identities too: the last stated identity wins in both directions ('nurse, no wait, insurance agent')
    spans += [(s0, e0) for s0, e0, _t in C._hits(ft, lex["non_clinical"])]
    return sorted(set(spans))


def role_correction(t, kb):
    """'Paediatrician... wait, actually internist', 'Kinderarzt, eigentlich Internist': the LAST stated role
    counts.  -> (t with the superseded role words blanked, [superseded words]).  A correction cue counts only
    when a role word follows it closely (at most three words) and another role word stands before it; a role
    after a possessive ('actually her cardiologist said ...') is somebody else."""
    spans = _role_spans(t, kb)
    if len(spans) < 2:
        return t, []
    for cue in reversed(list(CORRECTION_RX.finditer(t))):
        before = [sp for sp in spans if sp[1] <= cue.start()]
        after = [sp for sp in spans if sp[0] >= cue.end()]
        if not before or not after:
            continue
        a0 = after[0][0]
        gap = t[cue.end():a0]
        mention = _POSS.search(gap) and not re.search(r"(?:i mean|ich meine|je veux dire|quiero decir|volevo dire)\s",
                                                      cue.group(0) + " ")  # 'I mean her lawyer' is the asker
        if len(re.findall(r"[^\W_][\w'-]*", gap)) > 3 or mention or re.search(r"[;.!?]", gap):
            continue
        # deny wins: a first-person non-clinical identity ('Ich bin Journalistin, eigentlich Ärztin') is never
        # corrected away; a bare leading word is ('student, I mean the on-call surgeon')
        before = [sp for sp in before if not _FIRST_PERSON.search(t[:sp[0]])]
        if not before:
            return t, []
        return blank(t, before), [t[s0:e0] for s0, e0 in before]
    return t, []


# ----------------------------------------------------------------- entry point

def analyse(text, store):
    """-> {"clean": normalised text with instruction spans blanked, "task": clean text with exclusion spans
    blanked too, "excluded_text": the excluded phrases, "instructions": [snippets], "other_patient": reason}"""
    t = norm_text(text)
    ins = instruction_spans(t)
    clean = blank(t, ins)
    from .kb import kb as load_kb
    clean, superseded = role_correction(clean, load_kb())
    exc = exclusion_spans(clean)
    return {"clean": clean, "task": blank(clean, exc), "excluded_text": " | ".join(clean[s:e] for s, e in exc),
            "exclusion_spans": exc, "instructions": [t[s:e].strip() for s, e in ins],
            "other_patient": other_patient(text, store), "superseded_roles": superseded}

