"""KB routing (operating guide, online workflow steps 2-5 and 7).

situation text -> role (aliases, EN + DE, fuzzy at a fixed threshold) -> bundles (tags, EN + DE)
-> implied bundles (e.g. B04 adds B05) -> slots (union, best priority wins) -> role modifiers
-> link rules evaluated on the facts -> detail filter (short = P1, long = P1 + P2 + P3).

Deterministic.  The optional LLM layer (engine/llm.py, SECOND_LOOK_LLM=1) reads every request; its
proposal is merged with IDs that exist in the KB only: it may ADD bundles to the rules result, and set the
role only when the rules found none or a fuzzy (low-confidence) match.  An alias match always wins over
the model's role (guide step 3).  Timeout, error or budget stop -> the rules result alone.
"""
import difflib
import re

from . import llm
from .clinical import excluded_word, is_clinical_word
from .kb import bundle_tags, role_aliases
from .slots import drug_classes_of, found, rx
from .understand import _phrase_rx, _you_are_spans, extract_modifiers, fold, norm_text

FUZZY_THRESHOLD = 0.85        # fixed, per the guide; only aliases of 5+ characters are fuzzy-matched
SAFETY_RULES = {"R01", "R02", "R03", "R10", "R17"}   # allergies, blood thinners, contrast reaction/metformin: add at P1
PRIO_RANK = {"P1": 1, "P2": 2, "P3": 3}
LLM_EXTRA_WITH_RULES = 1     # bundles the LLM may add when the rules matched a task (up to 3 when they did not)


# Rules whose when_task/when_fact the engine evaluates on the facts.  when_task is satisfied by the rule
# being listed on a chosen bundle (bundles carry their rules); when_fact is checked here.
ANTITHROMBOTIC = ("antiplatelet", "anticoagulant_vka", "anticoagulant_doac", "heparin")


def _classes(c, ids):
    return any(set(ids) & set(c["current_classes"]))


def _icd(c, prefixes):
    return any(str((f.get("code") or {}).get("value") or "").upper().startswith(prefixes)
               for f in c["store"].facts if f.get("category") == "diagnosis"
               and (f.get("attrs") or {}).get("assertion") not in ("negative", "suspected")
               and str(f.get("date") or "")[:10] <= c["as_of"])


RULE_CHECKS = {
    "R01": lambda c: _classes(c, ANTITHROMBOTIC) or bool(c["found"]("med_antithrombotic")),
    "R02": lambda c: any(rx(r"contrast|kontrastmittel|\bkm\b|iodin").search(_t(f)) for f in c["found"]("allergies")),
    "R03": lambda c: _classes(c, ("biguanide",)),
    "R04": lambda c: _icd(c, ("E10", "E11", "E12", "E13", "E14", "I50", "I10", "I11", "I12", "I13", "I14", "I15")),
    "R05": lambda c: _classes(c, ("ace_inhibitor", "arb", "diuretic", "nsaid")),
    "R06": lambda c: _classes(c, ("glp1_agonist",)),
    "R07": lambda c: _icd(c, ("E10", "E11", "E12", "E13", "E14")),
    "R08": lambda c: _classes(c, ("ace_inhibitor", "arb")),
    "R09": lambda c: bool(c["found"]("carotid_stenosis")),
    "R10": lambda c: _classes(c, ANTITHROMBOTIC) or bool(c["found"]("med_antithrombotic")),
    "R11": lambda c: True,
    "R12": lambda c: bool(c["found"]("lvef") or c["found"]("coronary_hf")),
    "R13": lambda c: bool(c["found"]("cardiac_device")),
    "R14": lambda c: len({str(f.get("date"))[:10] for f in c["found"]("weight") if f.get("date")}) >= 2,
    "R15": lambda c: bool(c["found"]("discharge_followups")),
    "R16": lambda c: len(set(c["current_classes"])) >= 2,
    "R17": lambda c: bool(c["found"]("allergies")),
    "R18": lambda c: not c["found"]("lvef") or _icd(c, ("I50",)),
    "R19": lambda c: bool(c["found"]("carotid_stenosis")),
    "R20": lambda c: bool(c["found"]("valves")),
}
# Implemented elsewhere: R21 (staleness, fill.latest_by_key) and R22 (label panel, kbfill.label_panel).
RULES_IN_FILL = {"R21", "R22"}


def _t(f):
    from .fill import fact_text
    return fact_text(f)


# ----------------------------------------------------------------- role and bundles

def _blank_alias(t, alias):
    """t with every occurrence of the role alias (matched on the folded form) replaced by spaces."""
    out = list(t)
    for m in _phrase_rx(fold(norm_text(alias)), True).finditer(fold(t)):
        out[m.start():m.end()] = " " * (m.end() - m.start())
    return "".join(out)


def match_role(t, kb):
    spans = _you_are_spans(t)
    ft = fold(t)
    best = None
    for idx, role in enumerate(kb.roles):
        for alias in role_aliases(role):
            for m in _phrase_rx(fold(norm_text(alias)), True).finditer(ft):
                score = len(alias) + (100 if any(a <= m.start() < b for a, b in spans) else 0) \
                    - (0.5 if role.get("generic") else 0)  # a generic name ('doctor') loses ties to a specialty
                key = (score, -idx)
                if best is None or key > best[0]:
                    best = (key, role["id"], alias, "alias")
    if best:
        return best[1], best[2], best[3]
    # specialty word stems in several languages (rulebook/kb_overlay.json role_stems): the first word in the
    # text that starts with a stem names the role (cardiolog- / kardiyolog-, onkolog- ...)
    stems = [(rid, s_) for rid, sts in ((getattr(kb, "overlay", None) or {}).get("role_stems") or {}).items()
             if not rid.startswith("_") and rid in kb.role_by_id for s_ in sts]
    if stems:
        for m in re.finditer(r"[^\W\d_][\w-]*", ft):
            w = m.group(0)
            for rid, s_ in stems:
                if w.startswith(fold(s_)) and not excluded_word(w):
                    return rid, w, "stem"
    words = re.findall(r"[^\W\d_][\w&-]*", t)
    grams = words + [" ".join(words[i:i + 2]) for i in range(len(words) - 1)]
    best = None
    for role in kb.roles:
        for alias in (role.get("aliases_en") or []) + (role.get("aliases_de") or []):  # not the short intl names
            a = norm_text(alias)
            if len(a) < 5:
                continue
            for g in grams:
                # a typo keeps its first letter; a distinct clinical word is never a typo of another role
                # ('urologist' is not 'neurologist', 'rheumatologist' not 'pneumologist')
                if g[:1] != a[:1] or is_clinical_word(g):
                    continue
                r = difflib.SequenceMatcher(None, g, a).ratio()
                if r >= FUZZY_THRESHOLD and (best is None or r > best[0]):
                    best = (r, role["id"], alias)
    if best:
        return best[1], best[2], "fuzzy"
    return None, None, "none"


PREFIX_MIN = 6   # tags of 6+ characters also match as a word prefix (German compounds: Prämedikation-svisite)


def _tag_hits(t, tag):
    """Spans where a bundle tag matches: the exact phrase; for multi-word tags all words in one sentence
    (any order: 'review of blood pressure' ~ 'blood pressure review'); single words fuzzy at the fixed
    threshold (typos)."""
    nt = fold(norm_text(tag).strip())
    t = fold(t)
    out = [(m.start(), m.end()) for m in _phrase_rx(nt, len(nt) < PREFIX_MIN).finditer(t)]
    if out:
        return out
    words = nt.split()
    if len(words) > 1:
        for sm in re.finditer(r"[^.;:!?]+", t):
            sent, base, spans = sm.group(0), sm.start(), []
            for w in words:
                m = _phrase_rx(w, len(w) < PREFIX_MIN).search(sent)
                if not m:
                    break
                spans.append((base + m.start(), base + m.end()))
            else:
                out.append((min(a for a, _ in spans), max(b for _, b in spans)))
        return out
    if len(nt) >= PREFIX_MIN:
        for m in re.finditer(r"[^\W\d_][\w-]+", t):
            if abs(len(m.group(0)) - len(nt)) <= 2 and \
                    difflib.SequenceMatcher(None, m.group(0), nt).ratio() >= FUZZY_THRESHOLD:
                out.append((m.start(), m.end()))
    return out


def match_bundles(t, kb):
    """-> {bundle_id: (score, [tags])}.  A tag inside a longer tag match of another bundle is dropped
    (longest match wins); score = number of non-overlapping tag matches."""
    hits = []
    for b in kb.bundles:
        if b["id"] == kb.fallback_bundle:
            continue
        for tag in bundle_tags(b):
            if tag.startswith("("):
                continue
            for s0, e0 in _tag_hits(t, tag):
                hits.append((s0, e0, b["id"], tag))
    keep = [h for h in hits if not any(o[0] <= h[0] and h[1] <= o[1] and (o[1] - o[0]) > (h[1] - h[0])
                                       and o[2] != h[2] for o in hits)]
    out = {}
    for bid in {h[2] for h in keep}:
        mine = sorted((h for h in keep if h[2] == bid), key=lambda h: (h[0], -(h[1] - h[0])))
        spans, tags = [], []
        for s, e, _b, tag in mine:
            if any(s < pe and ps < e for ps, pe in spans):
                continue
            spans.append((s, e))
            tags.append(tag)
        out[bid] = (len(spans), tags)
    return out


def choose_bundles(matched, role):
    if not matched:
        return []
    defaults = (role or {}).get("default_bundles") or []
    in_def = [b for b in matched if b in defaults]
    if in_def:  # the role's own bundles, plus another bundle only if its tags clearly dominate
        best = max(matched[b][0] for b in in_def)
        keep = in_def + [b for b in matched if b not in defaults and matched[b][0] > best]
    else:
        best = max(v[0] for v in matched.values())
        keep = [b for b in matched if matched[b][0] == best]
    return sorted(keep, key=lambda b: int(b[1:]))


def expand(kb, bundle_ids):
    out = list(bundle_ids)
    i = 0
    while i < len(out):
        for x in kb.bundle_by_id[out[i]].get("implies") or []:
            if x not in out:
                out.append(x)
        i += 1
    return out


# ----------------------------------------------------------------- slots

def _better(p, q):
    return q is None or PRIO_RANK[p] < PRIO_RANK[q]


def assemble(kb, store, bundles, role, as_of, text):
    info = {}

    def put(slot, pr, origin, why=None, sources=(), rule=None):
        e = info.setdefault(slot, {"priority": None, "origins": [], "why": None, "source_ids": [], "rules": []})
        if _better(pr, e["priority"]):
            e["priority"] = pr
        e["origins"].append(origin)
        if why and not e["why"]:
            e["why"] = why
        for s in sources:
            if s not in e["source_ids"]:
                e["source_ids"].append(s)
        if rule and rule not in e["rules"]:
            e["rules"].append(rule)

    for bid in bundles:
        b = kb.bundle_by_id[bid]
        for pr in ("P1", "P2", "P3"):
            for s in (b.get("slots") or {}).get(pr) or []:
                put(s, pr, "%s %s" % (bid, pr), (b.get("why_overrides") or {}).get(s), b.get("sources") or [])
    for m in (role or {}).get("modifiers") or []:
        put(m["slot"], m["priority"], "role %s %s" % (role["id"], m["priority"]), None, role.get("sources") or [])

    # link rules listed on the chosen bundles
    from .kb import source_ids
    cur = current_meds(store, as_of)
    ctx = {"store": store, "as_of": as_of, "current_classes": [c for f in cur for c in drug_classes_of(kb, f)],
           "found": _found_cache(store, kb, as_of, text)}
    listed = []
    for bid in bundles:
        for r in kb.bundle_by_id[bid].get("rules") or []:
            if r not in listed:
                listed.append(r)
    fired, not_fired = [], []
    for rid in sorted(listed):
        rule = kb.rule_by_id[rid]
        check = RULE_CHECKS.get(rid)
        if check is None:
            continue
        if not check(ctx):
            not_fired.append(rid)
            continue
        fired.append(rid)
        pr = "P1" if rid in SAFETY_RULES else "P2"
        for s in rule.get("surface") or []:
            if s in kb.slot_by_id:
                put(s, pr, "rule %s %s" % (rid, pr), rule.get("display"), source_ids(rule.get("sources")), rid)
    for s, e in info.items():
        if not e["why"]:
            only_rules = all(o.startswith("rule ") for o in e["origins"])
            rule = kb.rule_by_id.get(e["rules"][0]) if e["rules"] else None
            e["why"] = (rule.get("display") if only_rules and rule else None) or kb.slot_by_id[s].get("why")
        e["sources"] = kb.sources(e.pop("source_ids"))
    return info, {"listed": listed, "fired": fired, "not_fired": not_fired,
                  "in_fill": [r for r in listed if r in RULES_IN_FILL]}


def _found_cache(store, kb, as_of, text):
    cache = {}

    def f(slot):
        if slot not in cache:
            cache[slot] = found(store, kb, slot, as_of, text)
        return cache[slot]
    return f


def current_meds(store, as_of):
    meds = [f for f in store.facts if f.get("ips_section") == "medications" and str(f.get("date") or "")[:10] <= as_of]
    dates = [str(f.get("date"))[:10] for f in meds if f.get("status") == "current"] or \
            [str(f.get("date"))[:10] for f in meds if f.get("date")]
    latest = max(dates or [""])
    return [f for f in meds if str(f.get("date") or "")[:10] == latest or f.get("status") == "current"]


# ----------------------------------------------------------------- entry point

def route(text, kb, store, as_of, detail="long", use_llm=True, force_bundles=None, force_role=None):
    t = norm_text(text)
    role_id, alias, method = match_role(t, kb)
    if force_role and force_role != role_id and force_role in kb.role_by_id:  # role read earlier (e.g. by the LLM)
        role_id, alias, method = force_role, None, "llm"
    role = kb.role_by_id.get(role_id)
    t_task = t
    if alias:  # the words naming the role describe who asks, not the task
        t_task = _blank_alias(t, alias)
    matched = match_bundles(t_task, kb)
    chosen = choose_bundles(matched, role)
    how = "kb_alias_tags"
    llm_note, llm_used, llm_reason, llm_info, llm_focus = None, False, None, None, None
    if use_llm:
        # every request: the model's reading is merged in (rules result + LLM-added bundles); the role is
        # taken from the model only when the rules found none or only a fuzzy (low-confidence) match
        from .focus import concepts as record_concepts
        prop, llm_info = llm.propose(text, kb, record_concepts(store)[0])
        if prop:
            if prop.get("focus_concepts"):  # promoted by engine/focus.py after the clinical gate
                llm_focus = {"concepts": list(prop["focus_concepts"]), "reason": prop.get("reason") or None}
            rid = prop.get("role_id")
            if rid in kb.role_by_id and (not role or (method == "fuzzy" and rid != role_id)):
                role_id, role, alias, method = rid, kb.role_by_id[rid], None, "llm"
                t_task = t
                matched = match_bundles(t_task, kb)
                chosen = choose_bundles(matched, role)
                llm_used = True
            added = [b for b in prop.get("bundle_ids") or [] if b in kb.bundle_by_id and b not in chosen
                     and b != kb.fallback_bundle]
            if chosen:  # the rules already found the task: one extra bundle at most (no screen dumps)
                added = added[:LLM_EXTRA_WITH_RULES]
            if added:
                how = "kb_llm" if not chosen else "kb_alias_tags+llm"
                chosen = sorted(set(chosen) | set(added), key=lambda b: int(b[1:]))
                llm_used = True
                llm_note = "LLM added %s" % ", ".join(added)
            if llm_used:
                llm_reason = prop.get("reason") or None
    note = None
    if force_bundles:  # screen.py: a recognised role's own task when the wording is not recognised
        chosen, how = list(force_bundles), "role_default"
        note = "Task wording not recognised: showing what %s usually needs (%s)." % (
            ("a %s" % role["name"]) if role else "this role",
            ", ".join(kb.bundle_by_id[b]["title"] for b in force_bundles))
    if not chosen:
        chosen = [kb.fallback_bundle]
        how = "fallback"
        note = ("Role/task not recognised, showing general summary" if not role else
                "Task not recognised for %s: showing the general summary plus the role's own priorities" % role["name"])
    bundles = expand(kb, chosen)
    info, rules = assemble(kb, store, bundles, role, as_of, text)
    order = sorted(info, key=lambda s: (PRIO_RANK[info[s]["priority"]], kb.slot_order[s]))
    shown = [s for s in order if detail == "long" or info[s]["priority"] == "P1"]
    return {
        "text": text,
        "task_text": t_task,
        "role_id": role["id"] if role else "other",
        "role_label": role["name"] if role else "Not recognised",
        "role_match": {"method": method, "matched": alias},
        "bundle_ids": bundles,
        "bundles_matched": {b: {"score": v[0], "tags": v[1]} for b, v in matched.items()},
        "bundles_chosen": chosen,
        "implied": [b for b in bundles if b not in chosen],
        "task_ids": bundles,
        "task_labels": [kb.bundle_by_id[b]["title"] for b in bundles],
        "tasks_from": how,
        "fallback_note": note,
        "llm_note": llm_note,
        "llm_used": llm_used,
        "llm_reason": llm_reason,
        "llm": llm_info,
        "llm_focus_proposal": llm_focus,
        "rules": rules,
        "detail": detail,
        "slots": [{"slot": s, "priority": info[s]["priority"], "origins": info[s]["origins"]} for s in order],
        "slots_shown": shown,
        "slot_info": info,
        "modifiers": extract_modifiers(t),
        "method": "rules+llm" if llm_used else "rules",
        "rulebook": "kb %s" % kb.version,
    }
