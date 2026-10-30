"""Synthetic test videos for the QA checker (ffmpeg test sources + our mix).

    python3 -m video.qa.make_test_video            -> video/out/qa_test_good.mp4
    python3 -m video.qa.make_test_video --broken   -> video/out/qa_test_broken.mp4

"good" follows the storyboard exactly: one test pattern per scene (hard cut at
every boundary), fade from/to black, video/out/audio/mix.wav as audio.
"broken" is deliberately wrong (720p/25 fps, 4 s of black and silence mid-video,
a boundary cut 1.5 s late, audio 6 dB too loud) so `video.qa.check` must fail it.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "video" / "out"
SOURCES = ["testsrc2", "smptehdbars", "color=c=0x1d3557", "testsrc", "color=c=0x2a9d8f",
           "rgbtestsrc", "color=c=0x6d2e46", "testsrc2", "color=c=0x264653"]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--broken", action="store_true")
    ap.add_argument("--audio", type=Path, default=OUT / "audio" / "mix.wav")
    args = ap.parse_args(argv)
    sb = json.loads((ROOT / "video" / "storyboard.json").read_text())
    W, H, fps = (1280, 720, 25) if args.broken else (sb["width"], sb["height"], sb["fps"])
    scenes = sb["scenes"]
    end = max(s["end"] for s in scenes)

    inputs, chains = [], []
    for k, sc in enumerate(scenes):
        d = sc["end"] - sc["start"]
        if args.broken and sc["id"] == "switch":
            d += 1.5  # late cut into "disagree"
        if args.broken and sc["id"] == "disagree":
            d -= 1.5
        src = SOURCES[k % len(SOURCES)]
        sep = ":" if "=" in src else "="
        inputs += ["-f", "lavfi", "-i", f"{src}{sep}size={W}x{H}:rate={fps}:duration={d}"]
        txt = f"{sc['id']}  {sc['start']}-{sc['end']} s"
        dt = (f"drawtext=fontfile='{FONT}':text='{txt}':fontsize={H // 14}:fontcolor=white:"
              f"box=1:boxcolor=black@0.55:boxborderw=20:x=(w-tw)/2:y=(h-th)/2") if Path(FONT).exists() else "null"
        f = f"[{k}:v]format=yuv420p,{dt}"
        if args.broken and sc["id"] == "screen":
            f += ",drawbox=t=fill:c=black:enable='between(t,6,10)'"  # 40-44 s black
        chains.append(f + f"[v{k}]")
    n = len(scenes)
    concat = "".join(f"[v{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0,fade=t=in:st=0:d=0.5," \
             f"fade=t=out:st={end - 1.5}:d=1.5[v]"
    afilt = "[a_in]anull[a]"
    if args.broken:
        afilt = "[a_in]volume=6dB,volume=enable='between(t,40,44)':volume=0[a]"
    graph = ";".join(chains + [concat, f"[{n}:a]anull[a_in]", afilt])
    out = OUT / ("qa_test_broken.mp4" if args.broken else "qa_test_good.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    if not args.audio.exists():
        raise SystemExit(f"{args.audio} missing: run python3 -m video.audio.build first")
    cmd = ["ffmpeg", "-v", "error", "-y", *inputs, "-i", str(args.audio), "-filter_complex", graph,
           "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
           "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-t", str(end), "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    print("wrote", out)


if __name__ == "__main__":
    main()
