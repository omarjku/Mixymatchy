"""CLI:  python3 -m engine.query "<situation text>" [--as-of YYYY-MM-DD] [--brief] [--no-llm]

Prints the JSON screen.  --brief prints a compact human-readable view instead.
"""
import argparse
import json
import sys

from .screen import build_screen

MARK = {"consistent": "OK ", "conflicting": "!! ", "outdated": "OLD", "not_documented": " o ",
        "not_applicable": "n/a"}


def brief(screen):
    u = screen["understood"]
    out = ["Role: %s   Tasks: %s   as of %s   (%s)" % (u["role_label"], ", ".join(u["task_labels"]),
                                                     u["as_of_date"], u["method"])]
    out.append("-- safety strip")
    for c in screen["safety_strip"]:
        out.append("  [%s] %s: %s" % (MARK.get(c["status"], "?"), c["label_en"], c["value_en"][:160]))
    out.append("-- cards")
    for c in screen["cards"]:
        out.append("  [%s] %-5s %s: %s  {%s}" % (MARK.get(c["status"], "?"), c["priority"], c["label_en"],
                                                 c["value_en"][:200], ",".join(c["facts"][:6])))
    if screen.get("blind_spot"):
        out.append("-- blind spot: " + screen["blind_spot"]["summary_en"])
    out.append("-- contradictions (%s)" % screen["contradictions_source"])
    for c in screen["contradictions"]:
        out.append("  %s %s" % ("*" if c["relevant"] else " ", c["title_en"]))
    out.append("-- " + screen["proof_bar"]["summary_en"] + "   (%s ms)" % screen["timing_ms"])
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Second Look: situation text -> screen JSON")
    ap.add_argument("text", nargs="+")
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--brief", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args(argv)
    screen = build_screen(" ".join(a.text), as_of=a.as_of, use_llm=not a.no_llm)
    if a.brief:
        print(brief(screen))
    else:
        json.dump(screen, sys.stdout, ensure_ascii=False, indent=1)
        print()


if __name__ == "__main__":
    main()
