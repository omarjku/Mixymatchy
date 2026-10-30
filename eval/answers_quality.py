"""Answer quality of the one-call path (docs/DECISIONS.md 24, v3.1), local, no key, no network.

The model's output is mocked with the picks the live v3 probe (17dc336, real Haiku, 30 Oct) actually returned for
the defects of v3.1, and code renders them.  Every answer must:
  * show each concept once (no "Contrast media allergy" x3, no "Diabetes mellitus type II" x2, no HbA1c twice)
  * show every cited fact of a counted contradiction with its flag ("left (one letter says right)"), and never a
    minority side alone
  * be <= 300 characters (a matched task bundle's required answers: <= engine/cited.MAX_CHARS, the official cases)
  * be a sentence, not a semicolon list (at most one ';' per sentence)
plus each fixture's own expectations (gentamicin EN + DE -> kidney function not documented + metformin + diabetes,
no contrast allergy; Vorsorge -> no family / social filler; a role without a bundle -> its own topic).

    python3 -m eval.answers_quality        # prints each answer, exits 1 on any failure
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _r(facts=(), sentence="", nd=()):
    return {"kind": "clinical_question", "fact_ids": list(facts), "not_documented": list(nd), "sentence": sentence}


# (name, request, the model's live output (None: no answer, i.e. timeout / error), expectations)
FIXTURES = [
    ("carotid: right-side fact listed next to left", "Neurologist, carotid follow-up",
     _r(["F0128", "F0102", "F0141"], "{F0128}; {F0102}; {F0141}."),
     {"has": ["left (one letter says right)"], "not": [r"stenosis, right"], "bundle": True}),
    ("carotid: minority side alone", "Neurologist, carotid follow-up",
     _r(["F0102"], "{F0102}."),
     {"has": ["left (one letter says right)"], "not": [r"stenosis, right"], "bundle": True}),
    ("gentamicin EN: contrast allergy x3", "Emergency doctor, I'm about to give IV gentamicin.",
     _r(["F0212", "F0063", "F0085"], "{F0212}; {F0063}; {F0085}."),
     {"has": ["Not documented in the letters: kidney function", "Metformin", "diabetes mellitus type II"],
      "not": [r"(?i)contrast"]}),
    ("gentamicin DE: no model answer", "Notärztin, gleich Gentamicin i.v.", None,
     {"has": ["Not documented in the letters: kidney function", "Metformin", "diabetes mellitus type II"],
      "not": [r"(?i)contrast", r"Nothing specific"]}),
    ("contrast CT: duplicate allergy", "Radiologist, contrast CT tomorrow",
     _r(["F0212", "F0125", "F0248", "F0209"], "{F0212}; {F0125}; {F0248.name} {F0248.dose} {F0248.schedule}; {F0209}.",
        ["kidney function"]),
     {"has": ["ontrast media allergy", "Metformin", "kidney function"], "bundle": True}),
    ("Vorsorge: family / social filler", "Gynäkologin, Vorsorge",
     _r(["F0177", "F0244"], "{F0177}; {F0244}."),
     {"has": ["Not documented in the letters"], "not": [r"(?i)family"]}),
    ("diabetes review: diagnosis x2, HbA1c twice", "GP, diabetes review",
     _r(["F0209", "F0158", "F0110"], "{F0209}; {F0158}; {F0110}."),
     {"has": ["Metformin", "HbA1c 6.4%"], "bundle": True}),
    ("Kardiologe: no model answer, role without a bundle", "Kardiologe, Herzinsuffizienz Verlaufskontrolle", None,
     {"has": ["Not documented in the letters"], "not": [r"(?i)follow-up", r"(?i)ophthalmolog"]}),
    ("natural sentence kept", "what is her latest HbA1c?",
     _r(["F0110"], "Her latest is {F0110} ({F0110.date})."),
     {"has": ["Her latest is HbA1c 6.4% (14 June 2015)."]}),
]

FLAG_RX = re.compile(r"one letter says|letters say|disagree|BMI does not match|BMI mismatch|letters also give|"
                     r"says (?:left|right)", re.I)


def run_one(request, raw):
    from engine import onecall as O
    from engine.screen import build_screen
    O.set_model((lambda *_a: raw) if raw is not None else (lambda *_a: None))
    try:
        s = build_screen(request, use_llm=True, rulebook="kb")
    finally:
        O.set_model(None)
    return s


def check(s, exp):
    """-> list of failures for one answer."""
    from engine import cited as W
    from engine.data import store
    st = store()
    a = s.get("answer") or {}
    txt = a.get("text") or ""
    bad = []
    # 1. each concept once (the store facts the Source chips cite)
    cpts = []
    for src in a.get("sources") or []:
        f = next((st.fact_by_id[x] for x in src.get("facts") or [] if x in st.fact_by_id), None)
        if f is not None and len(src.get("facts") or []) == 1:
            cpts.append(W.concept(f))
    dup = {c for c in cpts if cpts.count(c) > 1}
    if dup:
        bad.append("duplicate concepts: %s" % sorted(dup))
    clauses = [re.sub(r"\W+", " ", c).strip().lower() for c in re.split(r"[;,.]| and ", txt) if len(c.strip()) > 12]
    rep = {c for c in clauses if clauses.count(c) > 1}
    if rep:
        bad.append("repeated text: %s" % sorted(rep))
    # 2. contradictions flagged
    idx = W.contradictions(st)
    cited = {x for src in a.get("sources") or [] for x in src.get("facts") or []}
    if cited & set(idx) and not FLAG_RX.search(txt):
        bad.append("a cited fact of a counted contradiction without its flag")
    # 3. length
    limit = W.MAX_CHARS if exp.get("bundle") else 300
    if len(txt) > limit:
        bad.append("%d characters (> %d)" % (len(txt), limit))
    # 4. a sentence, not a semicolon list
    for sent in W.sentences(txt):
        if sent.count(";") > 1:
            bad.append("semicolon list: %s" % sent[:80])
    if len(W.sentences(txt)) > 2:
        bad.append("more than 2 sentences")
    for h in exp.get("has") or []:
        if h.lower() not in txt.lower():
            bad.append("missing %r" % h)
    for n in exp.get("not") or []:
        if re.search(n, txt):
            bad.append("must not match %r" % n)
    return bad


def run(out=print):
    import tempfile
    from engine import llm_budget
    saved = {k: os.environ.get(k) for k in ("SECOND_LOOK_ROUTER", "SECOND_LOOK_V3_LOG")}
    os.environ["SECOND_LOOK_ROUTER"] = "v2"
    os.environ["SECOND_LOOK_V3_LOG"] = "0"
    tmp = tempfile.TemporaryDirectory()
    llm_budget.reset(os.path.join(tmp.name, "budget.json"))
    fails = {}
    try:
        for name, request, raw, exp in FIXTURES:
            s = run_one(request, raw)
            a = s.get("answer") or {}
            bad = check(s, exp)
            out("%s %s | %s | %d chars | origin %s" % ("ok  " if not bad else "FAIL", name, request,
                                                       len(a.get("text") or ""), a.get("origin")))
            out("     %s" % (a.get("text") or "-"))
            for b in bad:
                out("     - %s" % b)
            if bad:
                fails[name] = bad
    finally:
        llm_budget.reset()
        tmp.cleanup()
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    out("answers quality: %d/%d fixtures ok" % (len(FIXTURES) - len(fails), len(FIXTURES)))
    return fails


if __name__ == "__main__":
    raise SystemExit(1 if run() else 0)
