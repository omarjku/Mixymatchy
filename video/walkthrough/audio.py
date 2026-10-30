"""Soundtrack for walkthrough.html: a soft ambient pad and a subtle UI click on every tap.

python3 video/walkthrough/audio.py [out.wav]   (default video/out/walkthrough/audio.wav)
Tap times must match TAPS in walkthrough.html.
"""
import sys
import wave
from pathlib import Path

import numpy as np

SR = 48_000
DURATION = 30.0
TAPS = [4.4, 6.7, 15.6, 21.0, 22.0]


def pad(t: np.ndarray) -> np.ndarray:
    # Two slow-moving chords (Dmaj9 -> Bm9), each voice a few detuned sines, gently swelling
    chords = [[146.83, 220.0, 277.18, 329.63, 440.0], [123.47, 185.0, 246.94, 293.66, 369.99]]
    out = np.zeros_like(t)
    for i, chord in enumerate(chords):
        # crossfade between the chords every 7.5 s
        phase = (t / 7.5 + i) % 2
        w = np.clip(np.where(phase < 1, phase, 2 - phase) * 1.6 - 0.3, 0, 1)
        w = 0.5 - 0.5 * np.cos(np.pi * w)
        for f in chord:
            for d in (-0.6, 0.0, 0.7):
                out += w * np.sin(2 * np.pi * (f + d) * t + f) / (1 + f / 220)
    out *= 1 + 0.15 * np.sin(2 * np.pi * 0.11 * t)
    # one-pole low-pass to soften
    a = np.exp(-2 * np.pi * 1200 / SR)
    y = np.empty_like(out)
    acc = 0.0
    for n, x in enumerate(out):
        acc = (1 - a) * x + a * acc
        y[n] = acc
    return y / np.max(np.abs(y))


def click(n: int, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * 2300 * t) * np.exp(-t * 90) * 0.6
    tick = rng.standard_normal(n) * np.exp(-t * 600) * 0.4
    body = np.sin(2 * np.pi * 520 * t) * np.exp(-t * 60) * 0.35
    return tone + tick + body


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "out/walkthrough/audio.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    t = np.arange(int(SR * DURATION)) / SR
    mix = pad(t) * 0.16
    fade = np.clip(t / 2.0, 0, 1) * np.clip((DURATION - t) / 2.5, 0, 1)
    mix *= fade
    rng = np.random.default_rng(7)
    for tt in TAPS:
        c = click(int(SR * 0.12), rng) * 0.32
        i = int(tt * SR)
        mix[i:i + len(c)] += c[: len(mix) - i]
    mix = np.clip(mix, -1, 1)
    stereo = np.repeat((mix * 32767).astype(np.int16)[:, None], 2, axis=1)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(stereo.tobytes())
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
