"""LLM-primary request decision with a deterministic veto (docs/DECISIONS.md 16 and 19).

When the optional LLM layer answered (engine/llm.py, request_kind + requester_role + bundles), its reading
decides whether the request gets data; the rules are the fallback when it did not answer (no key, timeout,
error, budget stop).  Deny wins on either side: the rules VETO the LLM when they see a non-clinical
self-identity (engine/clinical.py: lexicon, deny-wins identity, policy, purpose, withdrawn claims), a greeting /
filler-only or injection-only request, or another patient (handled before routing).  The LLM can refuse what the
rules would allow; it can never supply a missing role, and it opens the record only for request_kind
'clinical_task' with a role the RULES found, never past a veto.
"""
import re

from . import intent as I

SPAM_MESSAGE = ("No answer: this request cannot be processed. Second Look answers clinical staff about a care task, "
                "e.g. 'Anaesthetist, pre-op check'.")
WORD = re.compile(r"[^\W\d_][\w'-]*")


def greeting_only(req, aliases=()):
    """The request without the requester's words is only greeting / filler / test words (or nothing)."""
    rest = I.role_free(req.get("task") or "", aliases)
    words = [w.strip("'-") for w in WORD.findall(rest)]
    return all(w in I.lexicon()["never"] for w in words if w)


def injection_only(req):
    """Instructions were blanked and nothing else is left."""
    return bool(req.get("instructions")) and not WORD.search(req.get("clean") or "")


def veto(gate, req, aliases=()):
    """-> reason the rules refuse regardless of the LLM, or None."""
    if gate.get("decision") == "not_clinical":
        return "non-clinical requester (rules)"
    if req.get("other_patient"):
        return "another patient (rules)"
    if injection_only(req):
        return "instructions only (rules)"
    if greeting_only(req, aliases):
        return "greeting / filler only (rules)"
    return None


def decide(u, gate, req, aliases=(), rules_task=False, app_items=(), rules_actionable=False):
    """-> None (no LLM reading, or the rules decide) or (verdict, reason, vetoed_by).
    verdict: 'veto' (rules refuse; the rules path produces the refusal screen), 'refuse', 'spam', 'no_task',
    'no_role' or 'data'.

    The model RESTRICTS freely (non_clinical_requester, spam_or_abuse, other_patient); it can say 'no task' only
    when the rules found no task either; and where the rules found both a role and a task, the rules route the
    request (the model may add one bundle in engine/route.py).  Data always needs a requester role found by the
    rules' clinical gate (exact or fuzzy); without one the answer is 'no_role' (who is asking) whatever the model
    says; without any clinical content word the rules can see (engine/intent.py) the answer is 'no_task'.  With a
    rules role and vague clinical wording the model's kind decides between data and 'no_task'."""
    kind = u.get("llm_kind")
    if not kind:
        return None
    why = u.get("llm_reason") or kind.replace("_", " ")
    v = veto(gate, req, aliases)
    if v:
        return "veto", why, v
    rules_role = gate.get("decision") in ("kb_role", "clinical_term")
    if kind == "non_clinical_requester":
        return "refuse", why, None
    if kind == "other_patient":
        if app_items:  # a sex- or age-specific item ('PSA' for a woman) is 'not applicable', not another patient
            return None
        return "refuse", why, None
    if kind == "spam_or_abuse":
        return "spam", why, None
    if not rules_role:  # SECURITY: the requester's role must come from the rules' clinical gate; the model can
        return "no_role", why, None  # never supply a missing role, whatever it answers
    if not rules_actionable:  # SECURITY: no clinical content the rules can see (greeting + role, filler): no data
        return "no_task", why, None
    if rules_task:  # the rules found who asks and what for: they route (the model only restricts / adds one)
        return None
    if kind == "no_task":
        return "no_task", why, None
    if kind == "clinical_task":
        return "data", why, None
    return None
