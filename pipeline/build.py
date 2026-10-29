"""Build entry point: python3 -m pipeline.build  (run from repo root)

Writes data/build/docs.json, passages.json, facts.json (+ build_log.json) per docs/contracts.md.
"""
import collections
import os
import sys

from .common import BUILD_DIR, norm_ws, number_in_quote, numbers_in, write_json
from .ctx import Context, load_docs
from .ibm import Linker
from .rules import run_rules

IPS_ORDER = ["problems", "allergies", "medications", "procedures", "results", "vital_signs",
             "past_illness", "plan_of_care", "social_history", "functional_status"]


def _nums(s):
    return set(n.replace(",", ".") for n in numbers_in(s))


def merge_ibm_into_rules(rule_facts, ibm_facts):
    by_key = collections.defaultdict(list)
    for r in rule_facts:
        by_key[(r["passage_ids"][0], r["category"])].append(r)
    rest = []
    merged = 0
    for i in ibm_facts:
        target = None
        iq = norm_ws(i["quote"])
        for r in by_key.get((i["passage_ids"][0], i["category"]), []):
            rq = norm_ws(r["quote"])
            if (iq in rq or rq in iq) and _nums(i["label_en"]) <= _nums(r["label_en"]) | _nums(r["quote"]):
                target = r
                break
        if target is None:
            # identical evidence (same passage, same quote) in another category -> same fact
            for r in rule_facts:
                if r["passage_ids"][0] == i["passage_ids"][0] and norm_ws(r["quote"]) == iq \
                        and _nums(i["label_en"]) <= _nums(r["label_en"]) | _nums(r["quote"]):
                    target = r
                    break
        if target is None:
            rest.append(i)
            continue
        merged += 1
        if not target.get("code") and i.get("code"):
            target["code"] = i["code"]
        target["attrs"]["confirmed_by_ibm"] = True
        target.setdefault("_ibm_ids", []).extend(i.get("_ibm_ids", []))
    return rule_facts + rest, merged


def dedupe_same_passage(facts):
    out = {}
    for f in facts:
        k = (tuple(f["passage_ids"]), f["category"], f["ips_section"], norm_ws(f["quote"]), f["label_en"], f["origin"])
        if f["origin"] == "ibm":
            k = (tuple(f["passage_ids"]), f["category"], f["ips_section"], norm_ws(f["quote"]), f["origin"])
        if k in out:
            g = out[k]
            g.setdefault("_ibm_ids", []).extend(f.get("_ibm_ids", []))
            if not g.get("code") and f.get("code"):
                g["code"] = f["code"]
            continue
        out[k] = f
    return list(out.values())


def merge_across_docs(facts, ctx):
    """Merge facts only when the same document text is repeated (identical passage + quote)."""
    groups = collections.OrderedDict()
    for f in facts:
        if len(f["passage_ids"]) != 1:
            groups[id(f)] = [f]
            continue
        p = ctx.pid[f["passage_ids"][0]]
        # only text repeated within the same period (same year) is merged; never across stays/years
        k = (f["ips_section"], f["category"], f["label_en"], f["status"], norm_ws(f["quote"]), norm_ws(p["text"]),
             ctx.docs[p["doc_id"]].date[:4])
        groups.setdefault(k, []).append(f)
    out = []
    n_merged = 0
    for fs in groups.values():
        base = fs[0]
        if len(fs) > 1:
            docs_seen = {ctx.pid[x["passage_ids"][0]]["doc_id"] for x in fs}
            if len(docs_seen) > 1:
                n_merged += len(fs) - 1
                pids = []
                for x in fs:
                    for pid in x["passage_ids"]:
                        if pid not in pids:
                            pids.append(pid)
                    if not base.get("code") and x.get("code"):
                        base["code"] = x["code"]
                    base.setdefault("_ibm_ids", []).extend(x.get("_ibm_ids", []) if x is not base else [])
                base["passage_ids"] = pids
                dates = sorted(x["date"] for x in fs if x["date"])
                base["date"] = dates[0] if dates else None
                if any(x["origin"] == "ibm" for x in fs) and all(x["origin"] == "ibm" for x in fs):
                    base["origin"] = "ibm"
                out.append(base)
                continue
            # same doc, same text twice (e.g. repeated mention in one passage) -> keep one
            out.append(base)
            continue
        out.append(base)
    return out, n_merged


def self_check(facts, ctx):
    kept, dropped = [], []
    for f in facts:
        why = None
        for pid in f["passage_ids"]:
            p = ctx.pid.get(pid)
            if p is None:
                why = "unknown passage %s" % pid
                break
            if f["quote"] not in p["text"] and norm_ws(f["quote"]) not in norm_ws(p["text"]):
                why = "quote not in passage %s" % pid
                break
        if not why and not f["quote"].strip():
            why = "empty quote"
        if not why:
            bad = [n for n in numbers_in(f["label_en"]) + numbers_in(f["attrs"]) if not number_in_quote(n, f["quote"])]
            if bad and not f["attrs"].get("calculated"):
                why = "numbers not in quote: %s" % sorted(set(bad))
        if why:
            dropped.append({"label_en": f["label_en"], "quote": f["quote"], "passage_ids": f["passage_ids"],
                            "origin": f["origin"], "reason": why})
        else:
            f["verified"] = True
            kept.append(f)
    return kept, dropped


def main():
    docs = load_docs()
    ctx = Context(docs)

    docs_out = {d.id: {"title": d.title, "date": d.date, "type": d.type, "display_text": d.text}
                for d in docs.values()}
    passages_out = [p for d in docs.values() for p in d.passages]
    for p in passages_out:
        assert docs_out[p["doc_id"]]["display_text"][p["start"]:p["end"]] == p["text"], p["id"]

    rule_facts, unknown_words = run_rules(ctx)
    linker = Linker(ctx)
    ibm_facts = linker.link_all()
    n_rule, n_ibm = len(rule_facts), len(ibm_facts)

    rule_facts = dedupe_same_passage(rule_facts)
    ibm_facts = dedupe_same_passage(ibm_facts)
    facts, n_ibm_merged = merge_ibm_into_rules(rule_facts, ibm_facts)
    facts, n_cross = merge_across_docs(facts, ctx)
    facts, dropped = self_check(facts, ctx)

    doc_rank = {d: i for i, d in enumerate(sorted(docs, key=lambda x: (docs[x].date, x)))}

    def sort_key(f):
        p = ctx.pid[f["passage_ids"][0]]
        return (doc_rank[p["doc_id"]], p["start"], IPS_ORDER.index(f["ips_section"]), f["category"], f["label_en"])

    facts.sort(key=sort_key)
    ibm_links = {}
    for i, f in enumerate(facts, 1):
        f["id"] = "f%04d" % i
        ids = [x for x in f.pop("_ibm_ids", []) if x]
        if ids:
            ibm_links[f["id"]] = ids
    key_order = ["id", "ips_section", "category", "code", "label_en", "attrs", "date", "date_precision", "status",
                 "quote", "passage_ids", "origin", "verified"]
    facts = [{k: f.get(k) for k in key_order} for f in facts]

    os.makedirs(BUILD_DIR, exist_ok=True)
    write_json(os.path.join(BUILD_DIR, "docs.json"), docs_out)
    write_json(os.path.join(BUILD_DIR, "passages.json"), passages_out)
    write_json(os.path.join(BUILD_DIR, "facts.json"), facts)
    write_json(os.path.join(BUILD_DIR, "build_log.json"), {
        "unmatched_ibm": linker.unmatched, "dropped_facts": dropped, "ibm_links": ibm_links,
        "unknown_gloss_words": sorted(unknown_words),
    })

    # ---- summary
    print("docs: %d   passages: %d (%s)" % (len(docs_out), len(passages_out),
          ", ".join("%s=%d" % kv for kv in sorted(collections.Counter(p["kind"] for p in passages_out).items()))))
    print("raw facts: rule=%d ibm=%d | ibm merged into rule facts: %d | cross-doc merges: %d | final: %d"
          % (n_rule, n_ibm, n_ibm_merged, n_cross, len(facts)))
    print("IBM mentions linked: %d, unmatched: %d" % (linker.matched, len(linker.unmatched)))
    for u in linker.unmatched:
        print("  UNMATCHED [%s] %s: %r" % (u["file"], u["doc_id"], u["text"]))
    print("dropped facts: %d" % len(dropped))
    for d in dropped:
        print("  DROPPED %s | %r | %s" % (d["reason"], d["label_en"], d["passage_ids"]))
    by_sec = collections.Counter(f["ips_section"] for f in facts)
    print("facts per ips_section:")
    for sec in IPS_ORDER:
        if by_sec.get(sec):
            cats = collections.Counter(f["category"] for f in facts if f["ips_section"] == sec)
            print("  %-17s %3d  %s" % (sec, by_sec[sec], ", ".join("%s=%d" % kv for kv in sorted(cats.items()))))
    print("origin: %s" % dict(collections.Counter(f["origin"] for f in facts)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
