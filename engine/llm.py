"""Optional LLM hook for the 'Understand' step.

The deterministic matcher in engine/understand.py is the default and is fully
working on its own.  This module only *proposes* a role/task reading of the
situation text; every proposal is validated against the rulebook IDs, and the
LLM never produces patient facts, statuses or 'not documented' decisions.

Enabled only when ALL of these hold:
  * environment variable SECOND_LOOK_LLM=1
  * ANTHROPIC_API_KEY is set
  * the `anthropic` package is importable
Otherwise every function returns None.
"""
import json
import os

MODEL = os.environ.get("SECOND_LOOK_LLM_MODEL", "claude-haiku-4-5")


def available():
    if os.environ.get("SECOND_LOOK_LLM") != "1" or not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except Exception:
        return False
    return True


def understand(text, role_ids, task_ids, timeout=4.0):
    """Return {"role_id": str, "task_ids": [str], "modifiers": {...}} or None.

    The result is untrusted: the caller keeps only IDs that exist in the rulebook.
    """
    if not available():
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(timeout=timeout)
        prompt = (
            "A clinician describes a situation. Map it to one role id and 1-3 task ids.\n"
            "Role ids: %s\nTask ids: %s\n"
            "Answer with JSON only: {\"role_id\": ..., \"task_ids\": [...], "
            "\"modifiers\": {\"drugs\": [], \"procedures\": [], \"side\": null}}\n\n"
            "Situation: %s" % (", ".join(role_ids), ", ".join(task_ids), text))
        msg = client.messages.create(model=MODEL, max_tokens=300,
                                     messages=[{"role": "user", "content": prompt}])
        raw = "".join(getattr(b, "text", "") for b in msg.content)
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return None
        out = json.loads(raw[start:end + 1])
        if not isinstance(out, dict):
            return None
        return out
    except Exception:
        return None
