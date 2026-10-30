"""Automated QA for the submission video.

    python3 -m video.qa.check [path.mp4] [--srt video/audio/captions.srt] [--out video/out/qa]

Writes video/out/qa_report.md plus images in video/out/qa/ (per-scene thumbnails,
contact sheet, waveform, spectrogram). Exit code 0 = every FAIL-level check
passed, 1 = at least one failed, 2 = the file could not be read.
Each check is PASS / FAIL / WARN / INFO; WARN never fails the run.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VIDEO = ROOT / "video"
STORYBOARD = VIDEO / "storyboard.json"
METRICS = VIDEO / "metrics.json"
DEFAULT_MP4 = VIDEO / "out" / "second-look.mp4"
DEFAULT_SRT = VIDEO / "audio" / "captions.srt"

# tolerances (edit here, they are echoed into the report)
MAX_SECONDS = 120.0
END_TOL = 1.0
LUFS_RANGE = (-16.0, -12.0)
MAX_TP = -1.0
SILENCE_DB = -50.0
SILENCE_MAX = 3.0
BOUNDARY_TOL = 0.5
SCDET_THRESHOLD = 8.0
FADE_IN = 1.0     # black allowed in the first second
FADE_OUT = 2.0    # and in the last two seconds
BLACK_AT_CUT = 0.6  # a dip to black this short is allowed at a scene boundary
MAX_CAPTION_GAP = 3.0


@dataclass
class Check:
    name: str
    status: str  # PASS FAIL WARN INFO
    detail: str
    rows: list = field(default_factory=list)


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def ffprobe(path: Path) -> dict:
    p = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    if p.returncode:
        raise RuntimeError(p.stderr.strip())
    return json.loads(p.stdout)


def fmt_t(t: float) -> str:
    return f"{t:6.2f}s"


# --------------------------------------------------------------------------- analyses
def loudness(path: Path) -> dict:
    p = run(["ffmpeg", "-nostats", "-hide_banner", "-i", str(path), "-map", "0:a:0",
             "-filter_complex", "ebur128=peak=true", "-f", "null", "-"])
    txt = p.stderr[p.stderr.rfind("Summary:"):]
    res = {}
    for line in txt.splitlines():
        s = line.strip()
        for key, tag in (("I", "I:"), ("LRA", "LRA:"), ("TP", "Peak:")):
            if s.startswith(tag):
                res[key] = float(s.split()[1])
    return res


def silences(path: Path) -> list[tuple[float, float]]:
    p = run(["ffmpeg", "-nostats", "-hide_banner", "-i", str(path), "-map", "0:a:0", "-af",
             f"silencedetect=n={SILENCE_DB}dB:d={SILENCE_MAX}", "-f", "null", "-"])
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", p.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", p.stderr)]
    out = []
    for i, s in enumerate(starts):
        out.append((max(s, 0.0), ends[i] if i < len(ends) else float("inf")))
    return out


def video_scan(path: Path) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """One decode pass at reduced size: blackdetect intervals and scdet scene changes."""
    p = run(["ffmpeg", "-nostats", "-hide_banner", "-i", str(path), "-map", "0:v:0", "-vf",
             f"scale=480:-2,blackdetect=d=0.1:pic_th=0.98:pix_th=0.10,"
             f"scdet=threshold={SCDET_THRESHOLD}", "-an", "-f", "null", "-"])
    blacks = [(float(a), float(b)) for a, b in
              re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", p.stderr)]
    cuts = [(float(t), float(s)) for s, t in
            re.findall(r"lavfi\.scd\.score: ([\d.]+), lavfi\.scd\.time: ([\d.]+)", p.stderr)]
    if not cuts:  # older/newer ffmpeg print order differs
        cuts = [(float(t), float(s)) for t, s in
                re.findall(r"lavfi\.scd\.time: ([\d.]+).*?lavfi\.scd\.score: ([\d.]+)", p.stderr)]
    return blacks, cuts


def parse_srt(path: Path) -> list[dict]:
    def ts(s):
        h, m, rest = s.split(":")
        sec, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000

    cues = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip()):
        lines = block.strip().splitlines()
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        a, b = [x.strip() for x in lines[1].split("-->")]
        cues.append({"i": lines[0].strip(), "start": ts(a), "end": ts(b), "text": " ".join(lines[2:])})
    return cues


# "one" is left out on purpose: it is far more often a pronoun than a metric
NUMBER_WORDS = {"zero": 0, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
                "fourteen": 14, "fifteen": 15, "twenty": 20, "hundred": 100}


def spoken_numbers(text: str) -> list[float]:
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)]
    nums += [float(NUMBER_WORDS[w]) for w in re.findall(r"[a-z]+", text.lower()) if w in NUMBER_WORDS]
    return nums


def flat_numbers(obj) -> dict[str, float]:
    out = {}

    def walk(o, prefix):
        if isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{prefix}.{k}" if prefix else k)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{prefix}[{i}]")
        elif isinstance(o, (int, float)) and not isinstance(o, bool):
            out[prefix] = float(o)
    walk(obj, "")
    return out


# --------------------------------------------------------------------------- images
def images(path: Path, scenes: list[dict], outdir: Path, has_audio: bool) -> list[str]:
    outdir.mkdir(parents=True, exist_ok=True)
    notes = []
    font = next((f for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                             "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                             "/Library/Fonts/Arial.ttf") if Path(f).exists()), None)
    thumbs = []
    for k, sc in enumerate(scenes):
        t = (sc["start"] + sc["end"]) / 2
        out = outdir / f"thumb_{k:02d}_{sc['id']}.png"
        label = f"{sc['id']}  {sc['start']}-{sc['end']}s  (frame @ {t:.1f}s)"
        vf = "scale=640:-2"
        if font:
            vf += (f",drawtext=fontfile='{font}':text='{label}':x=12:y=h-th-12:fontsize=22:"
                   "fontcolor=white:box=1:boxcolor=black@0.6:boxborderw=6")
        p = run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1",
                 "-vf", vf, str(out)])
        if p.returncode == 0 and out.exists():
            thumbs.append(out)
        else:
            notes.append(f"thumbnail failed for {sc['id']}: {p.stderr.strip()[:200]}")
    if thumbs:
        cols = 3
        rows = (len(thumbs) + cols - 1) // cols
        inputs, filt = [], []
        for i, t in enumerate(thumbs):
            inputs += ["-i", str(t)]
        pads = rows * cols - len(thumbs)
        chain = "".join(f"[{i}:v]" for i in range(len(thumbs)))
        if pads:
            for j in range(pads):
                filt.append(f"color=c=black:s=640x360:d=1[p{j}]")
                chain += f"[p{j}]"
        layout = "|".join(f"{(i % cols) * 640}_{(i // cols) * 360}" for i in range(rows * cols))
        filt.append(f"{chain}xstack=inputs={rows * cols}:layout={layout}[o]")
        p = run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filt), "-map", "[o]",
                 "-frames:v", "1", str(outdir / "contact_sheet.png")])
        if p.returncode:
            notes.append("contact sheet failed: " + p.stderr.strip()[:200])
    if has_audio:
        for name, lav in (("waveform.png", "showwavespic=s=1920x360:split_channels=1:scale=sqrt"),
                          ("spectrogram.png", "showspectrumpic=s=1920x720:legend=1:scale=log:stop=16000")):
            p = run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-filter_complex", f"[0:a:0]{lav}[o]",
                     "-map", "[o]", "-frames:v", "1", str(outdir / name)])
            if p.returncode:
                notes.append(f"{name} failed: " + p.stderr.strip()[:200])
    return notes


# --------------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", nargs="?", type=Path, default=DEFAULT_MP4)
    ap.add_argument("--srt", type=Path, default=DEFAULT_SRT)
    ap.add_argument("--out", type=Path, default=VIDEO / "out" / "qa", help="image directory")
    ap.add_argument("--report", type=Path, default=VIDEO / "out" / "qa_report.md")
    args = ap.parse_args(argv)

    sb = json.loads(STORYBOARD.read_text())
    scenes = sb["scenes"]
    sb_end = float(max(s["end"] for s in scenes))
    boundaries = sorted({float(s["start"]) for s in scenes} - {0.0})
    fade_windows = [(0.0, FADE_IN), (sb_end - FADE_OUT, sb_end + 5)]
    for s in scenes:  # optional per-scene intended fades: "fades": [[start, end], ...]
        fade_windows += [tuple(w) for w in s.get("fades", [])]

    checks: list[Check] = []
    add = lambda *a, **k: checks.append(Check(*a, **k))

    if not args.video.exists():
        print(f"video not found: {args.video}", file=sys.stderr)
        return 2
    try:
        info = ffprobe(args.video)
    except RuntimeError as e:
        print(f"ffprobe failed: {e}", file=sys.stderr)
        return 2
    vstreams = [s for s in info["streams"] if s["codec_type"] == "video"]
    astreams = [s for s in info["streams"] if s["codec_type"] == "audio"]
    dur = float(info["format"].get("duration", 0))

    # 1 duration
    ok = dur <= MAX_SECONDS and abs(dur - sb_end) <= END_TOL
    add("Duration", "PASS" if ok else "FAIL",
        f"{dur:.2f} s (limit {MAX_SECONDS:.0f} s; storyboard ends at {sb_end:.0f} s, tolerance ±{END_TOL} s)")

    # 2 format
    if vstreams:
        v = vstreams[0]
        num, den = (int(x) for x in v.get("avg_frame_rate", "0/1").split("/"))
        fps = num / den if den else 0
        ok = v["width"] == sb["width"] and v["height"] == sb["height"] and abs(fps - sb["fps"]) < 0.01
        add("Resolution and frame rate", "PASS" if ok else "FAIL",
            f"{v['width']}x{v['height']} @ {fps:.3f} fps, codec {v.get('codec_name')}, "
            f"pix_fmt {v.get('pix_fmt')} (want {sb['width']}x{sb['height']} @ {sb['fps']})")
    else:
        add("Resolution and frame rate", "FAIL", "no video stream")

    # 3 audio stream
    if astreams:
        a = astreams[0]
        add("Audio stream", "PASS", f"{a.get('codec_name')} {a.get('sample_rate')} Hz, "
                                    f"{a.get('channels')} ch, {float(a.get('duration', dur)):.2f} s")
    else:
        add("Audio stream", "FAIL", "no audio stream")

    # 4 loudness
    if astreams:
        L = loudness(args.video)
        i_ok = LUFS_RANGE[0] <= L.get("I", -99) <= LUFS_RANGE[1]
        tp_ok = L.get("TP", 99) <= MAX_TP
        add("Loudness (EBU R128)", "PASS" if i_ok and tp_ok else "FAIL",
            f"integrated {L.get('I')} LUFS (want {LUFS_RANGE[0]}..{LUFS_RANGE[1]}), true peak {L.get('TP')} dBTP "
            f"(want ≤ {MAX_TP}), LRA {L.get('LRA')} LU")

        # 5 silence
        sil = silences(args.video)
        bad = [(s, e) for s, e in sil
               if not any(s >= a - 0.05 and min(e, dur) <= b + 0.05 for a, b in fade_windows)]
        add("No unintended silence", "FAIL" if bad else "PASS",
            f"silence = below {SILENCE_DB} dBFS for > {SILENCE_MAX} s; found {len(sil)}, unintended {len(bad)}",
            rows=[f"{fmt_t(s)} – {fmt_t(e)}" for s, e in bad])

    # 6/7 black frames and scene changes
    if vstreams:
        blacks, cuts = video_scan(args.video)

        def allowed_black(s, e):
            if any(s >= a - 0.05 and e <= b + 0.05 for a, b in fade_windows):
                return True
            return (e - s) <= BLACK_AT_CUT and any(s - 0.3 <= bnd <= e + 0.3 for bnd in boundaries)

        bad = [(s, e) for s, e in blacks if not allowed_black(s, e)]
        add("Black frames only at intended fades", "FAIL" if bad else "PASS",
            f"{len(blacks)} black interval(s); allowed: first {FADE_IN} s, last {FADE_OUT} s, "
            f"≤ {BLACK_AT_CUT} s dips at scene boundaries; unintended {len(bad)}",
            rows=[f"{fmt_t(s)} – {fmt_t(e)}" for s, e in bad] or [f"{fmt_t(s)} – {fmt_t(e)} (ok)" for s, e in blacks])

        rows, missing = [], []
        for bnd in boundaries:
            near = [(t, sc) for t, sc in cuts if abs(t - bnd) <= BOUNDARY_TOL]
            sid = next(s["id"] for s in scenes if float(s["start"]) == bnd)
            if near:
                t, sc = max(near, key=lambda x: x[1])
                rows.append(f"{fmt_t(bnd)} → {sid}: cut at {t:.2f} s (Δ {t - bnd:+.2f} s, score {sc:.1f})")
            else:
                closest = min(cuts, key=lambda x: abs(x[0] - bnd)) if cuts else None
                rows.append(f"{fmt_t(bnd)} → {sid}: NO cut within ±{BOUNDARY_TOL} s"
                            + (f" (closest {closest[0]:.2f} s)" if closest else ""))
                missing.append(bnd)
        extra = [t for t, _ in cuts if all(abs(t - b) > BOUNDARY_TOL for b in boundaries)]
        # a strong cut 0.5-2 s away from an unmatched boundary means the edit is shifted: FAIL.
        # no cut at all near a boundary may just be a soft cross-fade: WARN.
        shifted = [b for b in missing if any(BOUNDARY_TOL < abs(t - b) <= 2.0 and sc >= 2 * SCDET_THRESHOLD
                                             for t, sc in cuts)]
        for b in shifted:
            rows.append(f"{fmt_t(b)}: a strong cut sits 0.5-2 s away, the scene change looks shifted")
        status = "FAIL" if shifted or len(missing) > 2 else ("WARN" if missing else "PASS")
        add("Scene changes match storyboard boundaries", status,
            f"scdet threshold {SCDET_THRESHOLD}: {len(cuts)} change(s), {len(boundaries) - len(missing)}/"
            f"{len(boundaries)} boundaries matched within ±{BOUNDARY_TOL} s; {len(extra)} cut(s) inside scenes "
            "(fine for in-scene animation). Soft cross-fades may not register: check the contact sheet.",
            rows=rows)

    # 8 captions
    srt_cues = []
    if args.srt.exists():
        srt_cues = parse_srt(args.srt)
        probs = []
        for a, b in zip(srt_cues, srt_cues[1:]):
            if b["start"] < a["end"]:
                probs.append(f"overlap: cue {a['i']} ends {a['end']:.2f} > cue {b['i']} starts {b['start']:.2f}")
            if b["start"] - a["end"] > MAX_CAPTION_GAP:
                probs.append(f"gap {b['start'] - a['end']:.1f} s between cue {a['i']} and {b['i']}")
        for c in srt_cues:
            if c["end"] <= c["start"]:
                probs.append(f"cue {c['i']} has non-positive length")
            if c["end"] > sb_end + 0.01:
                probs.append(f"cue {c['i']} ends after the storyboard ({c['end']:.2f} s)")
        empty = [s["id"] for s in scenes
                 if not any(c["start"] < s["end"] and c["end"] > s["start"] for c in srt_cues)]
        probs += [f"scene '{e}' has no caption" for e in empty]
        covered = sum(c["end"] - c["start"] for c in srt_cues)
        if srt_cues:
            lead, tail = srt_cues[0]["start"], sb_end - srt_cues[-1]["end"]
            if lead > MAX_CAPTION_GAP or tail > MAX_CAPTION_GAP:
                probs.append(f"uncovered start {lead:.1f} s / end {tail:.1f} s")
        add("Captions cover the timeline", "FAIL" if probs or not srt_cues else "PASS",
            f"{args.srt.relative_to(ROOT) if args.srt.is_relative_to(ROOT) else args.srt}: {len(srt_cues)} cues, "
            f"{covered:.1f} s of {sb_end:.0f} s captioned ({100 * covered / sb_end:.0f}%), "
            f"no overlaps, gaps ≤ {MAX_CAPTION_GAP} s, every scene captioned", rows=probs)
    else:
        add("Captions cover the timeline", "FAIL", f"{args.srt} not found")

    # images
    notes = images(args.video, scenes, args.out, bool(astreams))
    if notes:
        add("Images", "WARN", "; ".join(notes))

    # ---- rubric
    rubric: list[Check] = []
    rub = lambda *a, **k: rubric.append(Check(*a, **k))
    ids = {s["id"] for s in scenes}
    demo_scenes = [i for i in ("ask", "screen", "switch", "disagree") if i in ids]
    rub("Shows the demo (app on screen)", "WARN" if demo_scenes else "FAIL",
        f"storyboard has demo scenes {demo_scenes}; confirm on the contact sheet that real app "
        "screens (not mock-ups) are visible. Manual check.")
    text = " ".join(c["text"] for c in srt_cues).lower()
    works = [w for w in ("works", "every fact linked", "found", "checked") if w in text]
    doesnt = [w for w in ("not yet", "does not", "doesn't", "isn't", "still need", "only one", "await", "not wired", "missing")
              if w in text]
    rub("Says what works", "PASS" if works else "FAIL", f"phrases found in captions: {works or 'none'}")
    rub("Says what does not work", "PASS" if doesnt else "FAIL", f"phrases found in captions: {doesnt or 'none'}")
    rub("At most 2 minutes", "PASS" if dur <= MAX_SECONDS else "FAIL", f"{dur:.2f} s")
    if METRICS.exists():
        metrics = flat_numbers(json.loads(METRICS.read_text()))
        vals = {abs(v) for v in metrics.values()} | {v * 100 for v in metrics.values() if 0 < v <= 1}
        spoken = {}
        for c in srt_cues:
            for n in spoken_numbers(c["text"]):
                spoken.setdefault(n, []).append(c["i"])
        sc_res = [c for c in srt_cues if any(s["id"] in ("results", "disagree") and
                                             s["start"] <= c["start"] < s["end"] for s in scenes)]
        res_nums = sorted({n for c in sc_res for n in spoken_numbers(c["text"])})
        unmatched = [n for n in res_nums if n not in vals]
        rub("Numbers match video/metrics.json", "FAIL" if unmatched else "PASS",
            f"numbers spoken in disagree/results: {res_nums}; not found in metrics.json: {unmatched or 'none'}",
            rows=[f"{k} = {v:g}" for k, v in sorted(metrics.items())])
    else:
        rub("Numbers match video/metrics.json", "WARN",
            "video/metrics.json not present yet: cannot cross-check the spoken/on-screen numbers")
    rub("Public repo without data/, README architecture, metric results", "INFO",
        "not checkable from the video; see docs/HANDOFF.md section 8")

    failed = [c for c in checks + rubric if c.status == "FAIL"]
    write_report(args, dur, checks, rubric, failed)
    print(f"{'FAILED' if failed else 'PASSED'}: {len(failed)} failing check(s). Report: {args.report}")
    for c in checks + rubric:
        print(f"  [{c.status}] {c.name}: {c.detail}")
    return 1 if failed else 0


def write_report(args, dur, checks, rubric, failed):
    rel = lambda p: p.relative_to(args.report.parent) if p.is_relative_to(args.report.parent) else p
    icon = {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "WARN": "⚠️ WARN", "INFO": "ℹ️ INFO"}
    md = [f"# Video QA report", "",
          f"- File: `{args.video}`  ",
          f"- Duration: {dur:.2f} s  ",
          f"- Result: **{'FAILED' if failed else 'PASSED'}** ({len(failed)} failing check(s))", "",
          "Generated by `python3 -m video.qa.check`. FAIL = must fix before submitting; "
          "WARN = look at it yourself; INFO = context.", "",
          "## Technical checks", "", "| Status | Check | Detail |", "|---|---|---|"]
    for c in checks:
        md.append(f"| {icon[c.status]} | {c.name} | {c.detail} |")
    for c in checks:
        if c.rows:
            md += ["", f"### {c.name}", ""] + [f"- {r}" for r in c.rows]
    md += ["", "## Challenge rubric checklist", "",
           "From docs/CHALLENGE.md: video ≤ 2 min showing the demo, says what works and what does not; "
           "metric results on the 5 situations.", "", "| Status | Item | Detail |", "|---|---|---|"]
    for c in rubric:
        md.append(f"| {icon[c.status]} | {c.name} | {c.detail} |")
    for c in rubric:
        if c.rows:
            md += ["", f"### {c.name}", ""] + [f"- {r}" for r in c.rows]
    md += ["", "## Images", ""]
    for name in ["contact_sheet.png", "waveform.png", "spectrogram.png"]:
        p = args.out / name
        if p.exists():
            md += [f"![{name}]({rel(p)})", ""]
    thumbs = sorted(args.out.glob("thumb_*.png"))
    if thumbs:
        md += ["Per-scene thumbnails: " + ", ".join(f"[{t.stem[9:]}]({rel(t)})" for t in thumbs), ""]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(md))


if __name__ == "__main__":
    sys.exit(main())
