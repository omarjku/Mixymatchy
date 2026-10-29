"""Hard-coded clinical vocabulary: brand->generic map, ATC categories, German->English glossary.

Only terms/keywords live here, never document sentences.
"""
import re

# Brand (as written in the documents) -> English generic name.
BRAND_GENERIC = [
    ("Thrombo ASS", "acetylsalicylic acid"),
    ("Glucophage", "metformin"),
    ("Zocor", "simvastatin"),
    ("Blopress", "candesartan"),
    ("Oleovit D3", "colecalciferol"),
    ("Alendronat", "alendronic acid"),
    ("Actos", "pioglitazone"),
    ("Byetta", "exenatide"),
    ("Nitro-Spray", "glyceryl trinitrate"),
    ("Nitroglycerin", "glyceryl trinitrate"),
]

# IBM German ingredient name -> English generic (for IBM nodes)
INGREDIENT_EN = {
    "acetylsalicylsäure": "acetylsalicylic acid",
    "metformin": "metformin",
    "simvastatin": "simvastatin",
    "candesartan": "candesartan",
    "vitamin d3": "colecalciferol",
    "alendronsäure": "alendronic acid",
    "pioglitazon": "pioglitazone",
    "exenatid": "exenatide",
    "nitroglycerin": "glyceryl trinitrate",
    "thrombozytenaggregationshemmer": "antiplatelet agent",
}

ATC_CATEGORY = [
    ("C01DA", "nitrate"),
    ("B01", "antithrombotic"),
    ("A10", "glucose_lowering"),
    ("C09", "antihypertensive"),
    ("C08", "antihypertensive"),
    ("C07", "antihypertensive"),
    ("C03", "antihypertensive"),
    ("C02", "antihypertensive"),
    ("C10", "lipid_lowering"),
    ("M05", "bone_agent"),
    ("A11", "vitamin"),
]

GENERIC_CATEGORY = {
    "acetylsalicylic acid": "antithrombotic",
    "antiplatelet agent": "antithrombotic",
    "metformin": "glucose_lowering",
    "pioglitazone": "glucose_lowering",
    "exenatide": "glucose_lowering",
    "candesartan": "antihypertensive",
    "simvastatin": "lipid_lowering",
    "alendronic acid": "bone_agent",
    "colecalciferol": "vitamin",
    "glyceryl trinitrate": "nitrate",
}


def atc_category(code):
    if not code:
        return None
    for prefix, cat in ATC_CATEGORY:
        if code.startswith(prefix):
            return cat
    return "other_medication"


ROUTE_EN = {"oral": "oral", "s.c.": "s.c.", "i.v.": "i.v.", "p.o.": "oral"}
FORM_EN = {"tropfen": "drops", "injektionslösung": "solution for injection", "tabl.": "tablet",
           "spray": "spray", "st": "unit(s)", "dosen": "dose(s)"}

REACTION_EN = {"übelkeit": "nausea", "schwindel": "dizziness", "erbrechen": "vomiting",
               "exanthem": "rash", "juckreiz": "itching", "atemnot": "dyspnoea",
               "urtikaria": "urticaria", "kreislauf": "circulatory reaction"}
ALLERGEN_EN = {"km": "contrast media", "kontrastmittel": "contrast media",
               "penicillin": "penicillin", "jod": "iodine", "latex": "latex",
               "arzneimittel": "drug"}

# German -> English glossary for diagnosis / procedure / finding phrases. Ordered: specific first.
# Each entry: (regex, english). Matching is case-insensitive.
GLOSSARY = [(re.escape(b).replace("\\ ", r"\s*"), "%s (%s)" % (g, b)) for b, g in BRAND_GENERIC] + [
    (r"transient\w*|vorübergehend\w*|kurzzeitig\w*", "transient"),
    (r"meh?r?ere sekunden dauernd", "lasting several seconds"),
    (r"wg\.|wegen|aufgrund", "due to"),
    (r"leichte verdickung des linken ventrikels", "mild left ventricular thickening"),
    (r"fokalneurologischen ausfälle", "focal neurological deficits"),
    (r"strömungsgeräusch", "bruit"),
    (r"schwaches", "faint"),
    (r"über", "over"),
    # assertion / qualifiers
    (r"vd\.\s?a\.|verdacht auf", "suspected"),
    (r"st\.\s?p\.|z\.\s?n\.|status post", "history of"),
    (r"kein anhalt für", "no evidence of"),
    (r"keine zeichen der|ohne zeichen einer|keine anzeichen für ein|keine anzeichen für", "no signs of"),
    (r"sind nicht erkennbar|nicht erkennbar", "not seen"),
    (r"fragestellung:?", "question:"),
    (r"diagnose:", "diagnosis:"),
    (r"im rahmen des aufenthalts", "during the stay"),
    (r"zur sonographisch\w*", "for ultrasound work-up"),
    (r"hba1c", "HbA1c"),
    (r"dezente[mn]?", "mild"),
    (r"einweisungsdiagnose", "admission diagnosis"),
    (r"nächste geplanter|nächste geplante", "next planned"),
    (r"regelmäßige", "regular"),
    (r"wird empfohlen|werden empfohlen|empfohlen", "recommended"),
    (r"geplant", "planned"),
    (r"gut eingestellter|gut eingestellt", "well-controlled"),
    (r"geringgradige", "minor"),
    (r"bekannte[nr]?", "known"),
    (r"beginnende", "incipient"),
    (r"vereinzelte[nr]?", "isolated"),
    (r"prophylaktische", "prophylactic"),
    (r"hämodynamisch relevante", "haemodynamically relevant"),
    (r"maximal", "up to"),
    # oncology
    (r"invasiv(?:e[sn]?)? duktal\w*\s+mammakarzinom\w*", "invasive ductal carcinoma of the breast"),
    (r"mammakarzinom\w*|mamma-ca", "breast cancer"),
    (r"malignomsuspekte läsion|suspekte läsion", "suspicious lesion"),
    (r"auffällige[rn]? mammographie", "abnormal mammogram"),
    (r"ausdehnung des tumors", "tumour extent"),
    (r"hormonrezeptor", "hormone receptor"),
    (r"her2neu", "HER2"),
    (r"ki-?67-?proliferationsrate", "Ki-67 proliferation rate"),
    (r"positiv", "positive"),
    (r"negativ", "negative"),
    (r"histologie", "histology"),
    (r"stanzbiopsie", "core biopsy"),
    (r"formationen", "formations"),
    (r"quadrantenresektion", "quadrantectomy"),
    (r"intraoperativer bestrahlung|iort", "intraoperative radiotherapy (IORT)"),
    (r"vorsorge-mammographie", "screening mammography"),
    (r"mammographie|mammogarphie", "mammography"),
    (r"sonographie der brust\+axilla", "breast and axillary ultrasound"),
    (r"ultraschallgezielte", "ultrasound-guided"),
    (r"ultraschalluntersuchung", "ultrasound"),
    (r"sonographisch|sonographie", "ultrasound"),
    (r"biopsie", "biopsy"),
    # eye
    (r"amaurosis fugax", "amaurosis fugax"),
    (r"zav", "central retinal artery occlusion"),
    (r"hollenhorst-plaques", "Hollenhorst plaques"),
    (r"retinalen minderdurchblutung", "retinal hypoperfusion"),
    (r"fundus hypertonicus", "hypertensive fundus"),
    (r"fundus:", "fundus:"),
    (r"papillenödem", "papilloedema"),
    (r"hypertensive retinopathie", "hypertensive retinopathy"),
    (r"dezent ödematöse retina", "slightly oedematous retina"),
    (r"superior der fovea", "superior to the fovea"),
    (r"weiße", "white"),
    (r"sehverschlechterung|sehstörung|sehschwäche|sehbeeinträchtigung", "visual disturbance"),
    (r"partiellen sehverlust", "partial vision loss"),
    (r"augensymptomatik", "eye symptoms"),
    (r"auge", "eye"),
    (r"verletzungen, fremdkörper oder raumforderungen", "injuries, foreign bodies or masses"),
    # cardiovascular
    (r"pulmonale hypertonie", "pulmonary hypertension"),
    (r"hypertensive\w* krise|hypertensive entgleisung", "hypertensive crisis"),
    (r"art\.?\s*hypertonie|art\.?\s*htn|art ht", "arterial hypertension"),
    (r"hypertonie", "hypertension"),
    (r"perikarderguß|perikarderguss", "pericardial effusion"),
    (r"rechtsherzbelastung", "right heart strain"),
    (r"komplexen ventr\. arrhythmien", "complex ventricular arrhythmias"),
    (r"arrhythmien", "arrhythmias"),
    (r"vhf", "atrial fibrillation"),
    (r"sves", "supraventricular extrasystoles"),
    (r"arteriosklerotischer gefäßschaden", "atherosclerotic vascular damage"),
    (r"karotissiphon", "carotid siphon"),
    (r"a(?:rteria|\.)\s*carotis interna", "internal carotid artery"),
    (r"a\.\s*carotis", "carotid artery"),
    (r"abgangsstenose", "ostial stenosis"),
    (r"60%ige", "60%"),
    (r"art?h?eriosklerotische|atherosklerotische|artherosklerotische", "atherosclerotic"),
    (r"veränderungen im bereich", "changes"),
    (r"karotisbifurkation|carotisbifurkation", "carotid bifurcation"),
    (r"karotisarterie", "carotid artery"),
    (r"carotissklerose|karotissklerose", "carotid sclerosis"),
    (r"karotisstenose|carotisstenose", "carotid stenosis"),
    (r"stenose", "stenosis"),
    (r"verkalkte plaquebildungen", "calcified plaques"),
    (r"einengung durch kalkplaques", "narrowing by calcified plaques"),
    (r"sklerose intrakranieller gefäße", "sclerosis of intracranial vessels"),
    (r"ischämie", "ischaemia"),
    (r"blutung", "haemorrhage"),
    (r"24h-rr-messung|24h-rr", "24h ambulatory blood pressure monitoring"),
    (r"langzeit-ekg|lz-ekg", "Holter ECG"),
    (r"ekg", "ECG"),
    (r"transthorakales echokardiographie|transthorakale echokardiographie", "transthoracic echocardiography"),
    (r"abklärung mittels herzecho", "work-up by echocardiography"),
    (r"herzecho", "echocardiography"),
    (r"doppler/duplex sonographie", "Doppler/duplex ultrasound"),
    (r"duplexsonographie|duplex sonographie", "duplex ultrasound"),
    (r"carotis-doppler|karotis-doppler", "carotid Doppler ultrasound"),
    (r"us hirnversorgende arterien", "ultrasound of brain-supplying arteries"),
    (r"hirnversorgenden halsarterien", "brain-supplying neck arteries"),
    (r"halsarterien", "neck arteries"),
    (r"karotisgefäße", "carotid arteries"),
    (r"auskultation der karotiden", "auscultation of the carotids"),
    (r"anpassung der antihypertensiven therapie", "adjustment of antihypertensive therapy"),
    (r"blutdruckkontrollen", "blood pressure checks"),
    (r"augenkontrollen|augenärztliche kontrollen", "eye check-ups"),
    (r"schädel-ct", "head CT"),
    (r"rektale untersuchung", "rectal examination"),
    (r"labor", "laboratory tests"),
    (r"therapie", "therapy"),
    # metabolic / other
    (r"diabetes mellitus typ ii|diab\.\s*mell\.\s*ii|niddmii|dm\s?ii", "diabetes mellitus type II"),
    (r"vitamin-d-mangel", "vitamin D deficiency"),
    (r"osteoporose", "osteoporosis"),
    (r"übergewicht", "overweight"),
    (r"hypercholesterinämie", "hypercholesterolaemia"),
    (r"hyperlipidämie|hlp", "hyperlipidaemia"),
    (r"dyslipidämie", "dyslipidaemia"),
    (r"schlafapnoe", "sleep apnoea"),
    (r"liquorzirkulationsstörung", "CSF circulation disorder"),
    (r"gastroösophageale refluxkrankheit|gerd", "gastro-oesophageal reflux disease"),
    (r"axiale hiatushernie|hiatushernie", "axial hiatus hernia"),
    (r"systemischer lupus erythematodes|sle", "systemic lupus erythematosus"),
    (r"entzündliches geschehen", "inflammation"),
    (r"che", "cholecystectomy"),
    (r"schwindel", "dizziness"),
    (r"grad", "grade"),
    (r"monaten", "months"),
    (r"wochen", "weeks"),
    (r"arteria carotis|karotis|carotis|karotiden", "carotid"),
    # sides / small words
    (r"linken|linkes|linke|links|li\.|li|sin\.", "left"),
    (r"rechten|rechtes|rechte|rechts|re\.|re", "right"),
    (r"bds\.", "bilateral"),
    (r"brust|mamma", "breast"),
    (r"kein|keine", "no"),
    (r"mit", "with"),
    (r"und|\+", "and"),
    (r"oder", "or"),
    (r"bei", "with"),
    (r"ohne", "without"),
    (r"in|im", "in"),
    (r"an", "at"),
    (r"von|der|des", "of"),
    (r"zur", "for"),
    (r">", ">"),
]
DROP_WORDS = {"dezentem", "die", "das", "den", "dem", "eine", "einer", "eines", "ein", "wird", "werden", "sind",
              "ist", "am", "auf", "zu", "eine", "einem", "bereich", "mittels", "dezentem"}

_GLOSS = [(re.compile(r"(?<![\wäöüß])(?:" + rx + r")(?![\wäöüß])", re.I), en) for rx, en in GLOSSARY]


def gloss(text, unknown=None):
    """Phrase-level German->English gloss. Unknown words are dropped (and collected)."""
    cands = []  # longest match wins, then glossary order
    for i, (rx, en) in enumerate(_GLOSS):
        for m in rx.finditer(text):
            cands.append((-(m.end() - m.start()), i, m.start(), m.end(), en))
    taken = []  # (start, end, english)
    for _, _, ms, me, en in sorted(cands):
        if any(not (me <= s or ms >= e) for s, e, _ in taken):
            continue
        taken.append((ms, me, en))
    taken.sort()
    out = []
    pos = 0

    def residual(seg):
        for tok in re.findall(r"\d+(?:[.,/]\d+)*(?:%|mg|mcg|µg|ml|cm|mm|kg|g)?(?![\wäöü])|[\wäöüßÄÖÜ%°/.-]+|[(),;:?]", seg):
            t = tok.strip(".")
            if not t:
                continue
            if re.fullmatch(r"[(),;:?]", t):
                out.append(t)
            elif re.fullmatch(r"[\d.,/%-]+%?|[TNMVG]\d\w*|[IVX]+°?|\d+°|\d+(?:[.,]\d+)?(?:mg|mcg|µg|g|ml|cm|mm|kg)", t):
                out.append(t)
            elif t.lower() in DROP_WORDS:
                continue
            else:
                if unknown is not None:
                    unknown.add(t)

    for s, e, en in taken:
        residual(text[pos:s])
        out.append(en)
        pos = e
    residual(text[pos:])
    s = " ".join(out)
    s = re.sub(r"\s+([),;:?])", r"\1", s)
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\(\s*\)", "", s)
    s = re.sub(r"\s+", " ", s).strip(" ,;")
    s = re.sub(r"\b(\w+)( \1\b)+", r"\1", s, flags=re.I)
    s = re.sub(r"\b(in|at|on|with|for) of\b", r"\1", s)
    s = re.sub(r"\b(of|in|at|with|and|or|for)\s*$", "", s).strip()
    return s[:1].upper() + s[1:] if s else s


# MEL procedure codes -> English (fallback when gloss is empty)
MEL_EN = {
    "DL520": "24h ambulatory blood pressure monitoring", "DE520": "Holter ECG", "DE510": "ECG",
    "QE520": "Mammography", "ZA010": "Head CT", "ZN010": "Ultrasound-guided biopsy",
    "ZN610": "Ultrasound", "EA510": "Ultrasound of brain-supplying arteries",
    "EB510": "Carotid duplex ultrasound", "DZ510": "Transthoracic echocardiography",
    "QE530": "Breast ultrasound", "FC510": "Axillary ultrasound", "ZN510": "Core biopsy",
    "ZX899": "Laboratory tests", "ZV610": "Histology", "ZV620": "Histology", "ZV630": "Histology",
    "ZV635": "Histology", "HM100": "Cholecystectomy", "HM110": "Cholecystectomy",
    "QE040": "Quadrantectomy", "QE050": "Quadrantectomy", "ZN171": "Intraoperative radiotherapy",
    "HZ989": "Rectal examination",
}
