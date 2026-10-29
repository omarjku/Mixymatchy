"""Entry point: python3 -m compare.build  (run from repo root, after python3 -m pipeline.build)

Reads data/build/{docs,passages,facts}.json, writes data/build/compare.json.
"""
import os
import sys

from pipeline.common import BUILD_DIR, load_json, write_json

from .core import compare


def validate(result, passages, facts):
    """Every claim must point to an existing fact + passage and quote an exact substring."""
    pas = {p["id"]: p for p in passages}
    fids = {f["id"] for f in facts}
    errors = []

    def check(c, where):
        if c["fact_id"] not in fids:
            errors.append("%s: unknown fact %s" % (where, c["fact_id"]))
        p = pas.get(c["passage_id"])
        if p is None:
            errors.append("%s: unknown passage %s" % (where, c["passage_id"]))
        elif c["quote"] not in p["text"]:
            errors.append("%s: quote not in passage %s" % (where, c["passage_id"]))
        elif p["doc_id"] != c["doc_id"]:
            errors.append("%s: doc mismatch" % where)

    for c in result["contradictions"]:
        for cl in c["claims"]:
            check(cl, c["id"])
    for x in result["blind_spots"] + result["open_followups"]:
        for cl in x.get("claims", []) + x.get("evidence", []):
            check(cl, x["id"])
        for pid in x.get("passage_ids", []):
            if pid not in pas:
                errors.append("%s: unknown passage %s" % (x["id"], pid))
    for p in result["propagation"]:
        for e in p["chain"]:
            if e["passage_id"] and e["passage_id"] not in pas:
                errors.append("propagation %s: unknown passage %s" % (p["contradiction_ids"], e["passage_id"]))
    return errors


def main(build_dir=BUILD_DIR):
    paths = {k: os.path.join(build_dir, k + ".json") for k in ("docs", "passages", "facts")}
    missing = [p for p in paths.values() if not os.path.exists(p)]
    if missing:
        sys.exit("missing %s - run `python3 -m pipeline.build` first" % ", ".join(missing))
    docs, passages, facts = (load_json(paths[k]) for k in ("docs", "passages", "facts"))
    result = compare(docs, passages, facts)
    errors = validate(result, passages, facts)
    result["validation_errors"] = errors
    out = os.path.join(build_dir, "compare.json")
    write_json(out, result)
    c = result["counts"]
    print("compare.json: %d counted contradictions, %d documentation notes, %d blind spots "
          "(%d of %d important concepts missing from latest doc %s), %d/%d follow-ups open, "
          "%d propagation chains, %d validation errors"
          % (c["contradictions_counted"], c["documentation_notes"], c["blind_spots"],
             c["missed_if_only_latest_read"], c["important_concepts"], c["latest_doc"],
             c["open_followups"], c["followups_total"], len(result["propagation"]), len(errors)))
    for x in result["contradictions"]:
        print("  [%s] %s %s: %s" % (x["tier"], x["id"], x["kind"], x["summary_en"]))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
