"""Render the soundtrack: python3 -m video.audio.build [--with-voice] [--voice PATH]

Writes video/out/audio/{music,sfx,mix}.wav (48 kHz, 24-bit stereo), cues.json and
stats.json. mix.wav is mastered to about -14 LUFS integrated, true peak <= -1 dBTP
(measured with ffmpeg ebur128). With --with-voice, video/out/audio/voice.wav
(made by video/audio/make_voice.sh) is mixed on top and the music ducks under it.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from . import dsp, score
from .dsp import SR, n_of

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "video" / "out" / "audio"
TARGET_LUFS = -14.0
MAX_TP = -1.2  # leave a little headroom under the -1 dBTP QA limit


def voice_duck(voice: np.ndarray, depth_db: float = 9.0) -> np.ndarray:
    """Gain curve for the music bed: down depth_db while the voice speaks."""
    env = dsp.envelope_follow(voice, 0.04)
    active = (env > dsp.undb(-45) * max(env.max(), 1e-9) / dsp.undb(-6)).astype(float)
    hold = n_of(0.35)
    act = 1.0 - dsp.running_min(np.pad(1.0 - active, (hold, hold), constant_values=1.0), 2 * hold + 1)[:len(active)]
    act = dsp.box(act, n_of(0.12) | 1)
    return dsp.undb(-depth_db * act)


def master(mix: np.ndarray) -> tuple[np.ndarray, float, dict]:
    """Gain + limiter loop until integrated loudness is within 0.3 LU of target."""
    m0 = dsp.measure(mix)
    gain_db = TARGET_LUFS - m0["I"]
    ceiling = -1.6
    out, meas = mix, m0
    for _ in range(6):
        out, _ = dsp.limiter(mix * dsp.undb(gain_db), ceiling_db=ceiling)
        meas = dsp.measure(out)
        err = TARGET_LUFS - meas["I"]
        tp_bad = meas["TP"] > MAX_TP
        if tp_bad:
            ceiling -= (meas["TP"] - MAX_TP) + 0.2
        if abs(err) <= 0.3 and not tp_bad:
            break
        gain_db += err
    return out, gain_db, meas


def scene_stats(x: np.ndarray) -> list[dict]:
    sb = json.loads(score.STORYBOARD.read_text())
    mono = 0.5 * (x[0] + x[1])
    rows = []
    for sc in sb["scenes"]:
        seg = mono[n_of(sc["start"]):n_of(sc["end"])]
        if not len(seg):
            continue
        spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        f = np.fft.rfftfreq(len(seg), 1 / SR)
        cen = float(np.sum(f * spec) / (np.sum(spec) + 1e-12))
        bands = {}
        for name, lo, hi in (("sub<60", 20, 60), ("low60-250", 60, 250), ("mid250-2k", 250, 2000),
                             ("high2k-8k", 2000, 8000), ("air>8k", 8000, 20000)):
            sel = (f >= lo) & (f < hi)
            bands[name] = float(np.sum(spec[sel] ** 2))
        tot = sum(bands.values()) + 1e-12
        rows.append({"scene": sc["id"], "rms_dbfs": round(float(dsp.db(np.sqrt(np.mean(seg ** 2)))), 1),
                     "peak_dbfs": round(float(dsp.db(np.max(np.abs(seg)))), 1),
                     "centroid_hz": round(cen), **{k: round(100 * v / tot, 1) for k, v in bands.items()}})
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--with-voice", action="store_true", help="mix video/out/audio/voice.wav on top")
    ap.add_argument("--voice", type=Path, default=OUT / "voice.wav")
    args = ap.parse_args(argv)

    t0 = time.time()
    music, sfx, cues = score.build()
    N = music.shape[1]
    print(f"rendered score in {time.time() - t0:.1f} s ({N / SR:.2f} s of audio)")

    voice = None
    if args.with_voice:
        if not args.voice.exists():
            raise SystemExit(f"{args.voice} not found: run video/audio/make_voice.sh first (macOS)")
        v = dsp.read_wav(args.voice)
        voice = np.zeros((2, N))
        voice[:, :min(N, v.shape[1])] = v[:, :N]
        vm = dsp.measure(voice)
        voice *= dsp.undb(-17.0 - vm["I"])          # speech sits around -17 LUFS before master
        voice = dsp.fft_filter(voice, lambda f: dsp.highpass_mag(f, 80, 2))
        duck = voice_duck(voice)
        music = music * duck
        sfx = sfx * (0.5 + 0.5 * duck)

    mix = music + sfx + (voice if voice is not None else 0.0)
    mastered, gain_db, meas = master(mix)
    g = dsp.undb(gain_db)
    OUT.mkdir(parents=True, exist_ok=True)
    dsp.write_wav(OUT / "music.wav", np.clip(music * g, -0.98, 0.98))
    dsp.write_wav(OUT / "sfx.wav", np.clip(sfx * g, -0.98, 0.98))
    if voice is not None:
        dsp.write_wav(OUT / "voice_mixed.wav", np.clip(voice * g, -0.98, 0.98))
    dsp.write_wav(OUT / "mix.wav", mastered)
    final = dsp.ebur128(OUT / "mix.wav")
    stats = {"length_s": N / SR, "master_gain_db": round(gain_db, 2), "with_voice": voice is not None,
             "ebur128": final, "scenes": scene_stats(mastered)}
    (OUT / "cues.json").write_text(json.dumps(cues, indent=1))
    (OUT / "stats.json").write_text(json.dumps(stats, indent=1))
    print(f"mix.wav: I={final.get('I')} LUFS  LRA={final.get('LRA')} LU  TP={final.get('TP')} dBTP  "
          f"(gain {gain_db:+.1f} dB, {time.time() - t0:.1f} s)")
    for r in stats["scenes"]:
        print("  ", r)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
