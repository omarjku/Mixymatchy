"""Sanity-check the answer keys against the real documents.

    python3 -m eval.oracle

Builds an in-memory 'oracle' build in which every non-empty line of every
document is one fact (quote = line, label_en empty, date = doc date) and runs
the coverage check.  Items that fail here can only pass if the pipeline adds
English wording / attrs (or merges lines); they are listed so the keys can be
reviewed for achievability.  Prints nothing from the documents except passage ids.
"""
import os
import sys

from . import core

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def oracle_build(raw_dir):
    docs, passages, facts = {}, [], []
    ddir = os.path.join(raw_dir, "documents")
    for fn in sorted(os.listdir(ddir)):
        raw = core.load_json(os.path.join(ddir, fn))
        did = fn[:-5]
        dt = core.display_text_from_raw(raw["text"])
        date = raw.get("metadata", {}).get("date")
        docs[did] = {"title": "", "date": date, "type": "", "display_text": dt}
        pos = 0
        for i, line in enumerate(dt.split("\n")):
            if line.strip():
                pid = "%s:l%03d" % (did, i)
                passages.append({"id": pid, "doc_id": did, "section": None, "kind": "line",
                                 "start": pos, "end": pos + len(line), "text": line})
                facts.append({"id": pid, "label_en": "", "attrs": {}, "quote": line,
                              "date": date, "status": "unknown", "passage_ids": [pid]})
            pos += len(line) + 1
    return core.Build(docs, passages, facts)


def main():
    raw = os.path.join(ROOT, "data", "patient-0000-0001")
    keys = core.load_json(os.path.join(ROOT, "eval", "answer_keys.json"))
    b = oracle_build(raw)
    cov = core.check_coverage(b, keys)
    n = 0
    for q in cov:
        for it in q["items"]:
            if it["pass"]:
                print("ok    %s %-55s via %s" % (q["id"], it["name"][:55], ",".join(it["facts"][:4])))
            else:
                n += 1
                print("LABEL %s %-55s line-only missing %s" % (
                    q["id"], it["name"][:55], ", ".join(core.group_label(g) for g in it["missing"])))
        for h in q["forbidden_hits"]:
            print("FORB  %s %s" % (q["id"], h["id"]))
    print("%d item(s) need English label/attrs or multi-line facts" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
