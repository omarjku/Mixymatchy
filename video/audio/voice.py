"""Build video/out/audio/voice.wav from video/audio/captions.srt.

    python3 -m video.audio.voice              # macOS: `say` (Samantha, fallback Daniel)
    python3 -m video.audio.voice --fake       # anywhere: speech-like placeholder for testing

Each caption cue is spoken separately and placed at its start time. A line that
runs longer than its cue (+0.3 s slack) is sped up with ffmpeg atempo (max 1.25x);
anything still too long is reported so the script line can be shortened.
Usually called through video/audio/make_voice.sh.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from . import dsp
from .dsp import SR, n_of

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "video" / "out" / "audio"
SLACK = 0.3
MAX_TEMPO = 1.25


def parse_srt(path: Path) -> list[tuple[float, float, str]]:
    def ts(s):
        h, m, rest = s.strip().split(":")
        sec, ms = rest.split(",")
        return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000
    cues = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip()):
        lines = block.strip().splitlines()
        if len(lines) >= 3 and "-->" in lines[1]:
            a, b = lines[1].split("-->")
            cues.append((ts(a), ts(b), " ".join(lines[2:])))
    return cues


def pick_voice(preferred: list[str]) -> str:
    listing = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    names = {line.split()[0] for line in listing.splitlines() if line.strip()}
    for v in preferred:
        if v in names:
            return v
    raise SystemExit(f"none of the voices {preferred} is installed (System Settings > Accessibility > Spoken Content)")


def say_line(text: str, voice: str, rate: int, tmp: Path, window: float) -> tuple[np.ndarray, float]:
    aiff = tmp / "line.aiff"
    subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", str(aiff), text], check=True)
    x = dsp.read_wav(aiff)[0]
    # trim leading/trailing near-silence
    env = np.abs(x) > 1e-3
    if env.any():
        i0, i1 = np.argmax(env), len(env) - np.argmax(env[::-1])
        x = x[max(i0 - n_of(0.02), 0):i1 + n_of(0.05)]
    dur = len(x) / SR
    tempo = 1.0
    if dur > window + SLACK:
        tempo = min(dur / (window + SLACK), MAX_TEMPO)
        src = tmp / "in.wav"
        dst = tmp / "out.wav"
        dsp.write_wav(src, x)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", f"atempo={tempo:.4f}", str(dst)],
                       check=True)
        x = dsp.read_wav(dst)[0]
    return x, tempo


def fake_line(text: str, window: float, seed: int) -> np.ndarray:
    """Speech-like placeholder: glottal pulse train through moving formants, syllable envelope."""
    rng = np.random.default_rng(seed)
    n = n_of(window)
    t = dsp.tvec(n)
    f0 = 165 * (1 + 0.08 * np.sin(2 * np.pi * 0.7 * t + rng.uniform(0, 6))) * np.interp(t, [0, window], [1.05, 0.92])
    src = dsp.saw(f0, n) + 0.05 * rng.standard_normal(n)
    syl = max(len(text.split()) * 1.4, 1)
    rate = syl / window
    env = np.clip(np.sin(np.pi * rate * t) ** 2 * 1.3, 0, 1)
    out = np.zeros(n)
    for f1, f2 in ((500, 1500), (700, 1100), (300, 2300)):
        out += dsp.fft_filter(src, lambda f: dsp.bandpass_mag(f, f1, 2.5) + 0.6 * dsp.bandpass_mag(f, f2, 2.5))
    out *= env
    edge = n_of(0.03)
    out[:edge] *= np.linspace(0, 1, edge)
    out[-edge:] *= np.linspace(1, 0, edge)
    return out / (np.max(np.abs(out)) + 1e-9) * 0.5


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--srt", type=Path, default=HERE / "captions.srt")
    ap.add_argument("--out", type=Path, default=OUT / "voice.wav")
    ap.add_argument("--voices", default="Samantha,Daniel")
    ap.add_argument("--rate", type=int, default=165, help="words per minute for `say`")
    ap.add_argument("--fake", action="store_true", help="placeholder voice (no `say` needed)")
    ap.add_argument("--length", type=float, default=None, help="seconds (default: storyboard end)")
    args = ap.parse_args(argv)

    import json
    sb = json.loads((ROOT / "video" / "storyboard.json").read_text())
    length = args.length or float(max(s["end"] for s in sb["scenes"]))
    cues = parse_srt(args.srt)
    buf = np.zeros(n_of(length) + n_of(2))
    voice = None
    if not args.fake:
        if not shutil.which("say"):
            raise SystemExit("`say` not found: run on macOS, or use --fake for a placeholder")
        voice = pick_voice(args.voices.split(","))
        print("voice:", voice)
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        for k, (a, b, text) in enumerate(cues):
            window = b - a
            if args.fake:
                x, tempo = fake_line(text, window, k), 1.0
            else:
                x, tempo = say_line(text, voice, args.rate, tmp, window)
            dur = len(x) / SR
            flag = "  <-- too long, shorten this line" if dur > window + SLACK + 0.05 else ""
            print(f"{a:7.2f}-{b:7.2f}  {dur:5.2f}s  x{tempo:.2f}  {text}{flag}")
            i0 = n_of(a)
            buf[i0:i0 + len(x)] += x[:len(buf) - i0]
    buf = buf[:n_of(length)]
    dsp.write_wav(args.out, np.vstack([buf, buf]))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
