"""Export the numbers the submission video shows, by running the real system.

    python3 video/scripts/export_metrics.py            (from the repo root)
    python3 video/scripts/export_metrics.py --no-http  (skip the uvicorn latency run)
    python3 video/scripts/export_metrics.py --root=/path/to/checkout  (run another checkout's code)

Runs the deterministic engine through the FastAPI adapter (backend/app/adapter.py) on the 5 case
situations, scores the 15 expected answers with the same token logic as backend/tests/test_adapter.py
(eval.core over the facts on the screen only), reads contradictions / blind spots / follow-ups from
compare.json and the verification counts from the build, and optionally measures HTTP latency against a
real uvicorn process. Writes video/metrics.json.

video/metrics.json is git-ignored: it contains English labels and short quotes derived from the
patient letters. The video (video/remotion) reads only this file and video/storyboard.json, so every
number on screen is computed here, never typed into the video code.
"""
import argparse
import json
import os
import re
import socket
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# --root runs the system from another checkout (e.g. a clean `git archive HEAD` snapshot while the
# working tree is mid-edit); metrics.json is still written to this repo's video/ folder.
_r = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--root=")]
ROOT = Path(_r[0]).resolve() if _r else REPO
for p in (ROOT, ROOT / "backend"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app import adapter  # noqa: E402
from engine.test_engine import SITUATIONS  # noqa: E402  (title + description only, never the questions)
from eval.core import Build, eval_question, norm  # noqa: E402

OUT = REPO / "video" / "metrics.json"
ROLE_SITUATIONS = {"anaesthetist": "1", "surgeon": "2", "emergency": "4"}
ROLE_TITLES = {"anaesthetist": "Anaesthetist", "surgeon": "Surgeon", "emergency": "Emergency physician"}
# Generic document-type words -> English (not patient text).
DOC_TYPE_EN = {
    "Radiologischer Befund": "Radiology report",
    "Langzeit-EKG": "Holter ECG",
    "24h-RR-Messung": "24 h blood pressure",
    "Konsil für Augenheilkunde": "Ophthalmology consult",
    "Stat. Patientenbrief (Interne)": "Discharge letter",
    "Ambulanter Patientenbrief": "Outpatient letter",
    "Histologie-Befund": "Histology report",
}


def short(s, n=46):
    s = " ".join((s or "").split())
    if len(s) <= n:
        return s
    cut = s[: n - 1].rsplit(" ", 1)[0].rstrip(",;:(")
    return cut + "…"


def fact_dict(f):
    attrs = {"value": f.value, "unit": f.unit, "side": f.side, "status": f.status}
    return {"id": f.id, "label_en": f.label_en, "attrs": attrs, "date": f.date, "status": f.status,
            "passage_ids": f.segment_ids}


def all_facts(b):
    return [f for n in b.needs for f in n.facts + n.superseded] + list(b.blind_spot)


def card(n):
    trust = None
    if n.facts:
        ts = {f.trust for f in n.facts}
        trust = "conflicting" if "conflicting" in ts else "stale" if "stale" in ts else "consistent"
    value = short(n.facts[0].label_en, 50) if n.facts else (
        "not applicable" if n.status == "not_applicable" else "not documented")
    if n.computed:
        value = short("%s: %s" % (n.computed[0].label, n.computed[0].value))
    return {"need": n.need, "label": short(n.label, 44), "status": n.status, "trust": trust, "value": value,
            "facts": len(n.facts), "linked": all(f.segment_ids for f in n.facts)}


def is_antithrombotic(need, label):
    t = (need + " " + label).lower()
    return any(k in t for k in ("antithromb", "thinner", "antiplatelet"))


def pick(cards):
    """Cards the screen scene names: blood thinner, allergy, heart function, one not documented."""
    want = [lambda c: is_antithrombotic(c["need"], c["label"]),
            lambda c: "allerg" in c["need"] or "allerg" in c["label"].lower(),
            lambda c: "lvef" in c["need"] or "ejection" in c["label"].lower(),
            lambda c: c["status"] == "not_documented"]
    out = []
    for w in want:
        c = next((c for c in cards if w(c) and c not in out), None)
        if c:
            out.append(c)
    return out


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def http_latency(runs=3):
    """Start the real FastAPI app with uvicorn and time POST /briefing for each situation."""
    port = free_port()
    env = dict(os.environ, SITE_PASSWORD="")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "--app-dir", "backend", "app.main:app",
                             "--port", str(port), "--log-level", "warning"], cwd=ROOT, env=env)
    base = "http://127.0.0.1:%d" % port
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(base + "/health", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        times = {}
        for sid, text in SITUATIONS.items():
            ts = []
            for _ in range(runs):
                req = urllib.request.Request(base + "/briefing", data=json.dumps({"situation": text}).encode(),
                                             headers={"Content-Type": "application/json"})
                t0 = time.perf_counter()
                with urllib.request.urlopen(req, timeout=30) as r:
                    json.load(r)
                ts.append((time.perf_counter() - t0) * 1000)
            times[sid] = ts
        return times
    except Exception as e:  # noqa: BLE001
        print("HTTP latency run failed (%s); using in-process timings" % e, file=sys.stderr)
        return None
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def weight_view(w, computed):
    out = {"blind_spot": w["label_en"] if w else None, "computed": computed}
    m = w and re.search(r"(\d+) kg -> (\d+) kg \(([-+]\d+) kg, ([-+][\d.]+)%\) between (\S+) and (\S+)",
                        w["label_en"])
    if m:
        out.update({"from_kg": int(m.group(1)), "to_kg": int(m.group(2)), "delta_kg": int(m.group(3)),
                    "pct": float(m.group(4)), "from_date": m.group(5), "to_date": m.group(6),
                    "stated_in_letters": False})  # kind unstated_computed: no letter states the change
    return out


# Honest "what does not work yet": short phrasings of docs/HANDOFF.md "Next steps", each included only if
# the handoff still lists it (matched by keyword), so the video never claims more than the repo says.
NOT_YET = [
    ("security/", "PIN lock and audit log are built but not wired into the app"),
    ("Filter blind spots", "Blind spots and follow-ups are patient-wide, not yet filtered to the task"),
    ("TODO-cite", "Rulebook rows still need guideline citations and a second reviewer"),
    ("Optional LLM layer", "AI reading of unusual wording is optional and off by default"),
    ("Screen polish", "Screen polish: duplicate cards (allergy shown 3x) still to merge"),
    ("unseen situations", "More unseen roles to test with the medical team"),
]


def not_yet():
    md = (ROOT / "docs" / "HANDOFF.md").read_text(encoding="utf-8")
    sec = md.split("## 8.", 1)[1].split("\n## ", 1)[0] if "## 8." in md else ""
    return [text for key, text in NOT_YET if key in sec]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-http", action="store_true")
    ap.add_argument("--root", help="checkout to run the system from (default: this repo)")
    a = ap.parse_args()

    keys = json.loads((ROOT / "eval" / "answer_keys.json").read_text(encoding="utf-8"))
    st = adapter.engine_store()
    compare = json.loads((ROOT / "data" / "build" / "compare.json").read_text(encoding="utf-8"))
    build_log = json.loads((ROOT / "data" / "build" / "build_log.json").read_text(encoding="utf-8"))
    facts_json = json.loads((ROOT / "data" / "build" / "facts.json").read_text(encoding="utf-8"))
    passages_json = json.loads((ROOT / "data" / "build" / "passages.json").read_text(encoding="utf-8"))

    briefings, inproc = {}, {}
    for sid, text in SITUATIONS.items():
        ts = []
        for _ in range(3):
            t0 = time.perf_counter()
            b = adapter.build_briefing(text, use_llm=False)
            ts.append((time.perf_counter() - t0) * 1000)
        briefings[sid], inproc[sid] = b, ts

    questions = []
    for qid in sorted(k for k in keys if not k.startswith("_")):
        b = briefings[qid.split(".")[0]]
        facts = list({f.id: fact_dict(f) for f in all_facts(b)}.values())
        build = Build(st.docs, st.passages, facts)
        texts = {f["id"]: norm(f["label_en"] + " | " + " ".join(str(v) for v in f["attrs"].values() if v))
                 for f in facts}
        res = eval_question(build, qid, keys[qid], texts)
        questions.append({"id": qid, "pass": bool(res["pass"])})

    # The exact sentence the app capture types (frontend preset), understood by the same adapter.
    ask_text = "Anaesthetist, pre-operative check before quadrantectomy with IORT on 16 May 2016"
    t0 = time.perf_counter()
    ab = adapter.build_briefing(ask_text, use_llm=False)
    ask = {"text": ask_text, "role": ab.role, "task": ab.task, "as_of": ab.as_of, "needs": len(ab.needs),
           "ms": round((time.perf_counter() - t0) * 1000, 1),
           "not_documented": ab.stats["not_documented"], "facts_shown": ab.stats["facts_shown"]}
    shown = [f for b in briefings.values() for n in b.needs for f in n.facts]
    trace = {"facts_on_screen": len(shown), "linked": sum(1 for f in shown if f.segment_ids),
             "pct": round(100.0 * sum(1 for f in shown if f.segment_ids) / max(1, len(shown)), 1)}

    http = None if a.no_http else http_latency()
    lat = http or inproc
    situations = []
    for sid, b in briefings.items():
        title = SITUATIONS[sid].split(".")[0]
        situations.append({
            "id": sid, "title": title, "role": b.role, "task": b.task, "as_of": b.as_of,
            "facts_shown": b.stats["facts_shown"], "facts_verified": b.stats["facts_verified"],
            "not_documented": b.stats["not_documented"], "needs": len(b.needs),
            "median_ms": round(statistics.median(lat[sid]), 1), "max_ms": round(max(lat[sid]), 1),
            "passed": sum(q["pass"] for q in questions if q["id"].startswith(sid + ".")),
            "questions": sum(1 for q in questions if q["id"].startswith(sid + ".")),
        })

    # Role screens for the "screen" and "switch" scenes.
    role_needs = {r: [n.need for n in briefings[s].needs] for r, s in ROLE_SITUATIONS.items()}
    shared = set.intersection(*(set(v) for v in role_needs.values()))
    roles = {}
    for r, sid in ROLE_SITUATIONS.items():
        b = briefings[sid]
        cards = [card(n) for n in b.needs]
        own = [c for c in cards if c["need"] not in shared]
        # role-specific cards for the switch scene: documented ones first, then one "not documented"
        focus = [c for c in own if c["status"] == "documented"][:4] + [c for c in own if c["status"] != "documented"][:1]
        roles[r] = {
            "title": ROLE_TITLES[r], "situation": SITUATIONS[sid], "situation_title": SITUATIONS[sid].split(".")[0],
            "task": b.task, "as_of": b.as_of,
            "shared": [c for c in cards if c["need"] in shared][:4],
            "focus": focus, "cards_total": len(cards),
            "pick": pick(cards),
            "not_documented": [c["label"] for c in cards if c["status"] == "not_documented"][:5],
            "facts_shown": b.stats["facts_shown"],
        }

    # One real source click for the anaesthetist (blood thinner): German sentence + English label.
    b1 = briefings["1"]
    source = None
    seg_by_id = {s.id: s for s in adapter.segments()}
    for n in b1.needs:
        if is_antithrombotic(n.need, n.label):
            if n.facts and n.facts[0].segment_ids:
                f = n.facts[0]
                segs = sorted((seg_by_id[i] for i in f.segment_ids if i in seg_by_id),
                              key=lambda s_: (s_.doc_date, s_.id))
                seg = segs[0] if segs else None  # the app's source pane scrolls to the earliest letter
                doc = st.docs.get(seg.doc_id, {}) if seg else {}
                source = {"need": n.label, "label_en": f.label_en, "quote_de": seg.text if seg else "",
                          "segment_id": seg.id if seg else "", "doc_id": seg.doc_id if seg else "",
                          "doc_date": seg.doc_date if seg else "",
                          "doc_title_en": DOC_TYPE_EN.get(doc.get("title"), "Letter"),
                          "letters_repeating": len({s.split(":")[0] for x in n.facts for s in x.segment_ids})}
                break

    docs = [{"id": d, "date": v["date"], "title_en": DOC_TYPE_EN.get(v["title"], v["title"])}
            for d, v in sorted(st.docs.items(), key=lambda kv: (kv[1]["date"], kv[0]))]

    counted = [c for c in compare["contradictions"] if c["tier"] == "counted"]
    notes = [c for c in compare["contradictions"] if c["tier"] != "counted"]

    def claim_view(c):
        return [{"doc_id": x["doc_id"], "date": x["doc_date"], "asserted": short(x["asserted"], 40),
                 "passage_id": x["passage_id"]} for x in c["claims"]]

    contra_short = {
        "bmi_mismatch": "BMI does not match weight and height",
        "event_date": "Same event, two dates",
        "laterality": "Carotid stenosis: left or right?",
    }
    def sides(c):
        cl = c["claims"]
        if c["kind"] == "bmi_mismatch":
            m = re.search(r"BMI ([\d.]+) stated, but (\d+) kg at (\d+) cm gives ([\d.]+)", c["summary_en"])
            if m:
                return ({"text": "BMI %s written" % m.group(1), "date": cl[0]["doc_date"]},
                        {"text": "%s kg · %s cm → BMI %s" % (m.group(2), m.group(3), m.group(4)),
                         "date": cl[0]["doc_date"]})
        if c["kind"] == "laterality":
            m = re.search(r"(LEFT|RIGHT) in (\S+) vs (LEFT|RIGHT) in (\d+)", c["summary_en"])
            if m:
                odd = next((x for x in cl if x["passage_id"] == m.group(2)), cl[0])
                return ({"text": "%s · 1 passage" % m.group(1).lower(), "date": odd["doc_date"]},
                        {"text": "%s · %s passages" % (m.group(3).lower(), m.group(4)), "date": cl[0]["doc_date"]})
        a = cl[0]
        b = next((x for x in cl[1:] if x["asserted"] != a["asserted"]), cl[-1])
        return ({"text": short(a["asserted"], 34), "date": a["doc_date"]},
                {"text": short(b["asserted"], 34), "date": b["doc_date"]})

    contradictions = []
    for c in counted:
        left, right = sides(c)
        contradictions.append({"id": c["id"], "kind": c["kind"],
                               "headline": contra_short.get(c["kind"], c["kind"]),
                               "summary": c["summary_en"], "left": left, "right": right,
                               "claims": claim_view(c)[:4]})
    carotid_counts = None
    c05 = next((c for c in counted if c["kind"] == "laterality"), None)
    if c05:
        m = re.search(r"(LEFT|RIGHT) in \S+ vs (LEFT|RIGHT) in (\d+)", c05["summary_en"])
        if m:
            carotid_counts = {"odd_side": m.group(1).lower(), "odd": 1, "main_side": m.group(2).lower(),
                              "main": int(m.group(3))}

    carotid = next((p for p in compare["propagation"] if p["kind"] == "side"), None)
    chain = []
    if carotid:
        by_doc = {}
        for x in carotid["chain"]:
            e = by_doc.setdefault(x["doc_id"], {"doc_id": x["doc_id"], "date": x["date"], "sides": [],
                                                "conflict_side": None})
            if x.get("value"):
                e["sides"].append(x["value"])
            if x["status"] == "conflicting" and x.get("value") == "right":
                e["conflict_side"] = "right"
        for e in by_doc.values():
            sides = e.pop("sides")
            e["side"] = max(set(sides), key=sides.count) if sides else None
            e["mentions"] = len(sides)
            chain.append(e)

    weight = next((x for x in compare["blind_spots"] if x["kind"] == "unstated_computed"), None)
    w_computed = None
    for n in briefings["3"].needs:
        if n.computed:
            w_computed = {"label": n.computed[0].label, "value": n.computed[0].value,
                          "formula": n.computed[0].formula}
            break

    counts = compare["counts"]
    all_lat = [t for v in lat.values() for t in v]
    metrics = {
        "_about": "Generated by video/scripts/export_metrics.py from the real system. Git-ignored.",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "questions": questions,
        "correct": sum(q["pass"] for q in questions), "total": len(questions),
        "situations": situations,
        "latency": {"source": "http" if http else "in-process",
                    "median_ms": round(statistics.median(all_lat), 1), "slowest_ms": round(max(all_lat), 1),
                    "requests": len(all_lat)},
        "documents": docs,
        "facts": {"total": len(facts_json), "passages": len(passages_json),
                  "dropped_at_build": len(build_log.get("dropped_facts") or []),
                  "verified_at_load": len(st.facts),
                  "dropped_at_load": len(facts_json) - len(st.facts),
                  "unverified_on_screen": sum(x["facts_shown"] - x["facts_verified"] for x in situations),
                  "rule": sum(1 for f in facts_json if (f.get("source") or f.get("origin") or "").startswith("rule")),
                  "ibm": sum(1 for f in facts_json if "ibm" in str(f.get("source") or f.get("origin") or "").lower())},
        "contradictions": {"counted": counts["contradictions_counted"], "notes": counts["documentation_notes"],
                           "list": contradictions,
                           "notes_list": [short(c["summary_en"], 70) for c in notes]},
        "carotid_chain": chain,
        "blind_spot": {"missed": counts["missed_if_only_latest_read"], "important": counts["important_concepts"],
                       "latest_date": counts["latest_date"],
                       "examples": [short(x["label_en"], 40) for x in compare["blind_spots"]
                                    if x["kind"] == "dropped_from_latest"][:6]},
        "weight": weight_view(weight, w_computed),
        "carotid_counts": carotid_counts,
        "ask": ask,
        "traceability": trace,
        "not_yet": not_yet(),
        "followups": {"open": counts["open_followups"], "total": counts["followups_total"],
                      "open_list": [short(x["label_en"], 50) for x in compare["open_followups"] if x["is_open"]]},
        "roles": roles,
        "source_click": source,
    }
    OUT.write_text(json.dumps(metrics, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote %s: %d/%d correct, %d contradictions, %d of %d blind spot, slowest %s ms (%s)" % (
        OUT.relative_to(REPO), metrics["correct"], metrics["total"], counts["contradictions_counted"],
        counts["missed_if_only_latest_read"], counts["important_concepts"], metrics["latency"]["slowest_ms"],
        metrics["latency"]["source"]))
    return 0 if metrics["correct"] == metrics["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
