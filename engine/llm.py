"""Optional LLM layer for the 'Understand' step (KB rulebook): Claude Haiku reads the situation text.

The deterministic matcher (engine/route.py) always runs and is the fallback.  The model only *proposes*
a role id and 1-3 bundle ids, each constrained by structured outputs to enums of the real KB ids, plus a
one-line reason; code validates every id again.  It never produces patient facts, statuses or
'not documented' decisions, and it cannot authorise a requester: the clinical gate (engine/clinical.py)
decides on the text alone.

Focus facts: with the record's concept labels (engine/focus.concepts: deduplicated English diagnosis labels
plus result/plan categories, short labels only, no other patient text) the schema also asks for
`focus_concepts`, 0-5 labels from that enum.  Code keeps only labels of the record (max MAX_FOCUS) and
engine/focus.py maps them back to existing fact ids, shown as an 'AI-highlighted for this task' group after
the clinical gate.

Enabled only when ALL of these hold:
  * environment variable SECOND_LOOK_LLM=1
  * ANTHROPIC_API_KEY is set (or a test client is injected with set_client)
  * the `anthropic` package is importable
  * the budget guard (engine/llm_budget.py) allows the call
Otherwise propose() returns None and the rules result stands.  Timeout: SECOND_LOOK_LLM_TIMEOUT
(default 4 s, hard wall-clock limit) -> rules fallback.

Cost: the static part (instructions, role and bundle lists) is one cached system block; a call sends
~40 new input tokens and gets ~100-200 output tokens back.  Repeated situations hit an in-process LRU
cache and cost nothing.
"""
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout

from . import llm_budget

DEFAULT_MODEL = "claude-haiku-5-5"
MAX_BUNDLES = 3
MAX_FOCUS = 5
MAX_REASON = 200
NO_ROLE = "none"

_client = None            # injected by tests (set_client); otherwise built lazily from the environment
_client_lock = threading.Lock()
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="llm")
_static = {}              # (kb version, concepts) -> (system text, schema, role ids, bundle ids, concepts)


def model():
    return os.environ.get("SECOND_LOOK_LLM_MODEL", DEFAULT_MODEL)


def timeout_s():
    return float(os.environ.get("SECOND_LOOK_LLM_TIMEOUT", "4"))


def set_client(client):
    """Tests: use this object instead of anthropic.Anthropic() (None = back to the real client)."""
    global _client
    _client = client


def enabled():
    return os.environ.get("SECOND_LOOK_LLM") == "1"


def available():
    if not enabled():
        return False
    if _client is not None:
        return True
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except Exception:
        return False
    return True


def _get_client():
    global _client
    with _client_lock:
        if _client is None:
            import anthropic
            _client = anthropic.Anthropic(timeout=timeout_s(), max_retries=0)
        return _client


def status():
    """For /health: {enabled, calls_today, spend_eur_est, budget_eur, ...}."""
    s = llm_budget.budget().snapshot()
    return {"enabled": available(), "model": model(), "calls_today": s["calls_today"],
            "calls_total": s["calls_total"], "cache_hits": s["cache_hits"],
            "spend_eur_est": round(s["spend_eur"], 4), "budget_eur": s["budget_eur"],
            "max_calls_per_day": s["max_calls_per_day"], "stopped": llm_budget.budget().why_blocked()}


# ----------------------------------------------------------------- prompt (static, cached)

def _short(s, n):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def static_prompt(kb, concepts=()):
    """-> (system text, json schema, role ids, bundle ids, concepts); deterministic for a given KB and record
    (cache-stable).  concepts: the record's concept labels (engine/focus.concepts), may be empty."""
    concepts = tuple(concepts or ())
    key = (kb.version, id(kb), concepts)
    if key in _static:
        return _static[key]
    role_ids = [r["id"] for r in kb.roles]
    bundle_ids = [b["id"] for b in kb.bundles if b["id"] != kb.fallback_bundle]
    roles = []
    for r in kb.roles:
        aliases = list(dict.fromkeys((r.get("aliases_en") or [])[:4] + (r.get("aliases_de") or [])[:2]))
        roles.append("%s: %s (%s)" % (r["id"], r.get("name", r["id"]), ", ".join(aliases)))
    bundles = []
    for b in kb.bundles:
        if b["id"] == kb.fallback_bundle:
            continue
        tags = list(dict.fromkeys((b.get("tags_en") or [])[:5] + (b.get("tags_de") or [])[:2]))
        tags = [t for t in tags if not t.startswith("(")]
        bundles.append("%s: %s. %s [%s]" % (b["id"], b["title"], _short(b.get("description"), 90), ", ".join(tags)))
    system = (
        "You route a clinician's short request to the information they need from one patient's record.\n"
        "Read the situation (English or German, possibly with typos) and answer:\n"
        "- role_id: who is asking, from the role list; \"none\" if no role is stated or it is not on the list. "
        "Never guess a role from the task alone.\n"
        "- bundle_ids: 1-3 task bundles that match what the person is doing, most relevant first; "
        "an empty list if no bundle fits.\n"
        "- reason: one short plain-English line (max 20 words) explaining the reading, without patient facts.\n"
        + ("- focus_concepts: 0-5 labels, copied exactly from the record concept list, that this person needs "
           "highlighted for this task, most important first: especially a condition the task bundles may not "
           "cover but that changes the plan (e.g. a comorbidity that is a caution for the planned treatment, "
           "or the condition the task names). An empty list when nothing stands out.\n" if concepts else "") +
        "You only classify the request. Do not judge whether the requester may see data.\n\n"
        "Roles (id: name (aliases)):\n" + "\n".join(roles) + "\n\n"
        "Task bundles (id: title. description [tags]):\n" + "\n".join(bundles) + "\n"
        + ("\nRecord concepts (labels present in this patient's record):\n" + "\n".join(concepts) + "\n"
           if concepts else "")
    )
    schema = {
        "type": "object",
        "properties": {
            "role_id": {"type": "string", "enum": role_ids + [NO_ROLE]},
            "bundle_ids": {"type": "array", "items": {"type": "string", "enum": bundle_ids}},
            "reason": {"type": "string"},
        },
        "required": ["role_id", "bundle_ids", "reason"],
        "additionalProperties": False,
    }
    if concepts:  # 0-5 is enforced in validate() (array length constraints are not supported by the API)
        schema["properties"]["focus_concepts"] = {"type": "array", "items": {"type": "string", "enum": list(concepts)}}
        schema["required"].append("focus_concepts")
    _static[key] = (system, schema, role_ids, bundle_ids, concepts)
    return _static[key]


def request_params(text, kb, concepts=()):
    system, schema, _r, _b, _c = static_prompt(kb, concepts)
    return dict(
        model=model(),
        max_tokens=1024,  # room for (low-effort) adaptive thinking plus the short JSON answer
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": "Situation: " + _short(text, 1000)}],
    )


# ----------------------------------------------------------------- call + validation

def validate(raw, kb, concepts=()):
    """Untrusted model output -> {"role_id": str|None, "bundle_ids": [...], "reason": str,
    "focus_concepts": [...]} or None.  focus_concepts: only labels of this record, deduplicated, at most
    MAX_FOCUS."""
    _s, _schema, role_ids, bundle_ids, concepts = static_prompt(kb, concepts)
    if not isinstance(raw, dict):
        return None
    rid = raw.get("role_id")
    rid = rid if isinstance(rid, str) and rid in role_ids else None
    given = raw.get("bundle_ids") if isinstance(raw.get("bundle_ids"), list) else []
    bids = []
    for x in given:
        if isinstance(x, str) and x in bundle_ids and x not in bids:
            bids.append(x)
    reason = raw.get("reason")
    reason = _short(reason, MAX_REASON) if isinstance(reason, str) else ""
    given = raw.get("focus_concepts") if isinstance(raw.get("focus_concepts"), list) else []
    allowed = set(concepts)
    focus = []
    for x in given:
        if isinstance(x, str) and x in allowed and x not in focus:
            focus.append(x)
    return {"role_id": rid, "bundle_ids": bids[:MAX_BUNDLES], "reason": reason, "focus_concepts": focus[:MAX_FOCUS]}


def _call(params):
    return _get_client().messages.create(**params)


def cache_key(text, kb, concepts=()):
    return (model(), kb.version, hash(tuple(concepts or ())), " ".join(str(text or "").lower().split()))


def propose(text, kb, concepts=()):
    """-> (proposal | None, info).  info = {"called": bool, "cached": bool, "skipped": str|None,
    "cost_eur": float}.  Never raises."""
    info = {"called": False, "cached": False, "skipped": None, "cost_eur": 0.0}
    if not available():
        info["skipped"] = "disabled"
        return None, info
    if not str(text or "").strip():
        info["skipped"] = "empty"
        return None, info
    b = llm_budget.budget()
    key = cache_key(text, kb, concepts)
    hit = b.cache_get(key)
    if hit is not None:
        info["cached"] = True
        return dict(hit), info
    if not b.reserve():
        info["skipped"] = b.why_blocked() or "budget"
        return None, info
    info["called"] = True
    try:
        params = request_params(text, kb, concepts)
        fut = _pool.submit(_call, params)
        msg = fut.result(timeout=timeout_s())
    except FutureTimeout:
        b.error()
        info["skipped"] = "timeout"
        return None, info
    except Exception as e:  # network, auth, rate limit, bad request: the rules result stands
        b.error()
        info["skipped"] = "error: %s" % type(e).__name__
        return None, info
    try:
        usage = getattr(msg, "usage", None)
        if usage is not None:
            info["cost_eur"] = b.record(params["model"], usage)
        if getattr(msg, "stop_reason", None) in ("refusal", "max_tokens"):
            info["skipped"] = "stop_reason: %s" % msg.stop_reason
            return None, info
        txt = next((getattr(x, "text", "") for x in msg.content if getattr(x, "type", None) == "text"), "")
        out = validate(json.loads(txt), kb, concepts)
    except Exception as e:
        b.error()
        info["skipped"] = "invalid: %s" % type(e).__name__
        return None, info
    if out is None:
        info["skipped"] = "invalid"
        return None, info
    b.cache_put(key, out)
    return dict(out), info


def understand(text, role_ids, task_ids, timeout=4.0):
    """Legacy rulebook hook (engine/understand.py): the LLM layer serves the KB rulebook only."""
    return None
