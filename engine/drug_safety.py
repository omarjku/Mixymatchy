"""A small drug-safety map (docs/DECISIONS.md 24, v3.1): a request that names a renally cleared or nephrotoxic drug
needs the kidney facts, the way a matched task bundle needs its P1 answers.

TODO-cite: the medical team still has to attach a reference (product information / guideline) to every row.  The
rows only choose WHICH of the letters' facts are shown (and which absence is stated); they never add a value.

    match(text, st) -> {"rows": [row ids], "facts": [store chunk ids "F0248"], "topics": ["kidney function"]}

facts   the newest current store fact of each listed kind (metformin, diabetes, contrast allergy), when the letters
        have one; never invented
topics  stated as "not documented in the letters" only when no fact's own words cover them (engine/onecall.topic_ok)
"""
from __future__ import annotations

import re

# drug pattern (English / German, folded) -> what the answer needs.  TODO-cite for every row.
ROWS = [
    {"id": "aminoglycoside",  # nephrotoxic, renally cleared
     "rx": r"gentami[cz]in|tobramy[cz]in|amika[cz]in|netilmi[cz]in|streptomy[cz]in|aminoglycosid|aminoglykosid",
     "needs": ["kidney_function", "metformin", "diabetes"]},
    {"id": "vancomycin", "rx": r"vancomy[cz]in|vankomy[cz]in",
     "needs": ["kidney_function", "metformin", "diabetes"]},
    {"id": "nsaid", "rx": r"\bnsaids?\b|\bnsar\b|ibuprofen|diclofenac|naproxen|ketoprofen|indometa[cz]in|etoricoxib|"
                          r"celecoxib|metamizol",
     "needs": ["kidney_function", "metformin", "diabetes"]},
    {"id": "contrast", "rx": r"contrast|kontrastmittel|\bkm\b|iodinated|jodhaltig",
     "needs": ["contrast_allergy", "kidney_function", "metformin"]},
    {"id": "metformin", "rx": r"metformin",
     "needs": ["kidney_function", "diabetes"]},
]
_RX = [(r, re.compile(r["rx"], re.I)) for r in ROWS]

# a need -> how to find its fact in the store (category + label words), or the topic stated when absent
NEEDS = {
    "kidney_function": {"categories": ("creatinine", "egfr", "kidney_function", "renal_function"),
                        "label": r"creatinin|kreatinin|\begfr\b|\bgfr\b|kidney function|renal function",
                        "topic": "kidney function"},
    "metformin": {"categories": ("glucose_lowering",), "label": r"metformin"},
    "diabetes": {"categories": ("diagnosis",), "label": r"^diabetes mellitus"},
    "contrast_allergy": {"categories": ("allergy",), "label": r"contrast"},
}


def _newest(st, need):
    """The newest fact of a need, current facts first -> the fact or None."""
    rx = re.compile(need["label"], re.I)
    hits = [f for f in st.facts if f.get("category") in need["categories"] and rx.search(f.get("label_en") or "")]
    if not hits:
        return None
    return max(hits, key=lambda f: (f.get("status") == "current", str(f.get("date") or ""), f["id"]))


def match(text, st):
    from .understand import fold
    from . import onecall as O
    t = fold(str(text or "")).lower()
    rows = [r for r, rx in _RX if rx.search(t)]
    out = {"rows": [r["id"] for r in rows], "facts": [], "topics": []}
    for r in rows:
        for n in r["needs"]:
            need = NEEDS[n]
            f = _newest(st, need)
            if f is not None:
                cid = O.fid(f)
                if cid in O.chunks(st) and cid not in out["facts"]:
                    out["facts"].append(cid)
            elif need.get("topic") and O.topic_ok(st, need["topic"]) and need["topic"] not in out["topics"]:
                out["topics"].append(need["topic"])
    return out
