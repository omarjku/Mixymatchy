"""Procedural score and sound design for the Second Look video.

120 BPM (one beat = 0.5 s, one bar = 2 s), D minor. Every storyboard boundary is
an integer second, so sections land on bar lines. Musical arc:
intro (hook) -> tension (problem, disagree) -> theme (screen, switch, how, results)
-> resolve (close, D major add9).

Sound-effect cue times default to the values in DEFAULT_CUES (absolute seconds).
A storyboard scene may override them with an optional "cues" object, e.g.
  {"id": "switch", ..., "cues": {"whoosh": [55.2, 59.8]}}
The cue times actually used are written to video/out/audio/cues.json.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from . import dsp
from .dsp import SR, midi_hz, n_of, place

ROOT = Path(__file__).resolve().parents[2]
STORYBOARD = ROOT / "video" / "storyboard.json"
BEAT = 0.5

DEFAULT_CUES = {
    # 8 letters stack up during "problem"
    "letter_tick": [9.0 + i * 1.25 for i in range(8)],
    # the anaesthetist types one sentence, then presses enter
    "typing": [23.0, 28.6],          # [start, end] of the keystroke burst
    "enter": [29.0],
    "chime": [44.0],                  # source sentence highlight
    "whoosh": [55.0, 59.5],           # lens morph: surgeon, emergency physician
    "alert": [66.0, 68.0, 70.0, 72.0, 74.0],  # one per contradiction
    "resolve": [76.0],
    "countup": [97.0, 99.0, 101.0, 103.0],    # metric count-ups
    "impact": [34.0, 96.0, 110.0],
}

# chord voicings (MIDI); bass root separately
CH = {
    "Dm9": (38, [50, 57, 60, 64, 65]),
    "Dmb6": (38, [50, 57, 58, 62, 65]),
    "Bbmaj7": (34, [46, 53, 57, 62, 72]),
    "Bbmaj7#11": (34, [46, 53, 57, 64, 69]),
    "F": (41, [53, 57, 60, 64, 67]),
    "C": (36, [48, 55, 62, 64, 67]),
    "Gm9": (43, [55, 58, 62, 65, 69]),
    "Gm/D": (38, [50, 58, 62, 67, 69]),
    "A7sus": (45, [57, 62, 64, 67, 69]),
    "A7": (45, [57, 61, 64, 67, 69]),
    "Eb": (39, [51, 58, 63, 67, 70]),
    "Fmaj9": (41, [53, 57, 64, 67, 69]),
    "Dadd9": (38, [50, 57, 62, 64, 66, 69, 74]),
}

THEME = ["Dm9", "Bbmaj7", "F", "C"]


def chord_plan() -> list[tuple[float, float, str]]:
    plan = [(0, 8, "Dm9"),
            (8, 12, "Dmb6"), (12, 16, "Bbmaj7#11"), (16, 20, "Gm/D"), (20, 22, "A7sus"),
            (22, 26, "Dm9"), (26, 30, "Bbmaj7"), (30, 32, "Gm9"), (32, 33, "A7sus"), (33, 34, "A7")]
    t = 34
    while t < 50:
        plan.append((t, t + 2, THEME[((t - 34) // 2) % 4]))
        t += 2
    plan += [(50, 52, "Dm9"),
             (52, 54, "Gm9"), (54, 56, "Bbmaj7"), (56, 58, "F"), (58, 60, "C"), (60, 62, "Gm9"),
             (62, 63, "A7sus"), (63, 64, "A7"),
             (64, 66, "Bbmaj7"), (66, 68, "Gm9"), (68, 70, "Bbmaj7"), (70, 72, "Gm9"),
             (72, 74, "Eb"), (74, 76, "A7"), (76, 80, "Fmaj9")]
    t = 80
    while t < 96:
        plan.append((t, t + 2, THEME[((t - 80) // 2) % 4]))
        t += 2
    plan += [(96, 98, "Dm9"), (98, 100, "Bbmaj7"), (100, 102, "F"), (102, 104, "C"),
             (104, 106, "Dm9"), (106, 108, "Bbmaj7"), (108, 109, "A7sus"), (109, 110, "A7"),
             (110, 118, "Dadd9")]
    return plan


# lead melody: (beat offset within 4-bar phrase, midi, beats)
MELODY_A = [(0, 74, 1.5), (1.5, 72, 0.5), (2, 69, 2),
            (4, 70, 1), (5, 69, 1), (6, 65, 2),
            (8, 72, 1.5), (9.5, 74, 0.5), (10, 76, 2),
            (12, 79, 1), (13, 76, 1), (14, 74, 2)]
MELODY_B = [(0, 77, 1), (1, 76, 0.5), (1.5, 74, 0.5), (2, 69, 2),
            (4, 74, 1), (5, 72, 1), (6, 70, 1), (7, 69, 1),
            (8, 72, 1), (9, 77, 1), (10, 76, 2),
            (12, 74, 1), (13, 72, 1), (14, 74, 2)]


def load_cues() -> tuple[dict, float]:
    sb = json.loads(STORYBOARD.read_text())
    cues = {k: list(v) for k, v in DEFAULT_CUES.items()}
    for sc in sb["scenes"]:
        for k, v in (sc.get("cues") or {}).items():
            cues[k] = list(v)
    end = max(sc["end"] for sc in sb["scenes"])
    return cues, float(end)


def in_ranges(t: float, ranges) -> bool:
    return any(a <= t < b for a, b in ranges)


class Score:
    def __init__(self, length: float):
        self.length = length
        self.N = n_of(length)
        z = lambda: np.zeros((2, self.N))
        self.pad, self.bass, self.drums, self.keys, self.lead = z(), z(), z(), z(), z()
        self.music_send, self.sfx, self.sfx_send = z(), z(), z()
        self.kicks: list[float] = []

    # ------------------------------------------------------------------ music
    def render_pads(self, plan):
        raw = np.zeros((2, self.N))
        rng = np.random.default_rng(11)
        for (a, b, name) in plan:
            _, notes = CH[name]
            gate = (b - a) + 0.25
            env = dsp.adsr(gate, 0.9 if a > 0 else 2.5, 1.5, 0.85, 1.6)
            n = len(env)
            for j, m in enumerate(notes):
                for det, pan in ((-7, -0.7), (0, 0.0), (7, 0.7)):
                    f = midi_hz(m + det / 100.0)
                    # slow vibrato for life
                    fv = f * (1 + 0.0015 * np.sin(2 * np.pi * 0.23 * dsp.tvec(n) + rng.uniform(0, 6)))
                    x = dsp.saw(fv, n, rng.uniform()) * env * (0.55 if j == 0 else 0.4)
                    place(raw, x, a - 0.1, pan=pan * (0.5 + 0.1 * j))
        # filter automation: dark intro, closed tension, open theme, wide finale
        pts = [(0, 250), (7.5, 1800), (8, 900), (21, 1400), (22, 1200), (33.5, 3000), (34, 4200),
               (52, 3400), (64, 1300), (75.5, 1800), (76, 3600), (80, 2200), (95.5, 5500),
               (96, 5200), (104, 3000), (110, 4200), (118, 1200)]
        ts, vs = zip(*pts)
        fc = lambda f, t: dsp.lowpass_mag(f, np.interp(t, ts, vs), order=2, res=0.35)
        filt = dsp.stft_filter(raw, fc, nfft=2048, hop=512)
        filt = dsp.fft_filter(filt, lambda f: dsp.highpass_mag(f, 110, 1))
        self.pad += dsp.widen(filt, 1.35) * 0.16 * dsp.ramp_curve(self.N, [(0, 1), (109, 1), (111, 1.5), (self.length, 1.5)])
        self.music_send += filt * 0.10

    def render_drone(self):
        # low tension drone under "problem" and "disagree": detuned D1/A1 saws, very dark
        for a, b, root in ((8, 22.5, 26), (64, 76.5, 34)):
            env = dsp.adsr(b - a, 2.0, 1.0, 1.0, 1.5)
            n = len(env)
            t = dsp.tvec(n)
            x = np.zeros(n)
            for m, g in ((root, 1.0), (root + 7, 0.6), (root + 12, 0.35)):
                for det in (-9, 9):
                    x += g * dsp.saw(midi_hz(m + det / 100), n)
            x = dsp.fft_filter(x, lambda f: dsp.lowpass_mag(f, 220, 2))
            x *= env * (0.8 + 0.2 * np.sin(2 * np.pi * 0.25 * t))  # slow throb
            place(self.pad, x * 0.09, a)
            # thin high shimmer cluster for unease
            sh = (dsp.sine(midi_hz(86), n) + 0.7 * dsp.sine(midi_hz(87.2), n)) * env
            sh = sh * (0.5 + 0.5 * np.sin(2 * np.pi * 0.11 * t))
            place(self.music_send, np.vstack([sh, np.roll(sh, n_of(0.013))]) * 0.012, a)

    def render_bass(self, plan, active):
        for (a, b, name) in plan:
            if not in_ranges(a, active):
                continue
            root, _ = CH[name]
            env = dsp.adsr(b - a - 0.02, 0.01, 0.6, 0.75, 0.12)
            n = len(env)
            f = midi_hz(root)
            x = dsp.sine(f, n) + 0.25 * dsp.sine(2 * f, n) + 0.08 * np.tanh(3 * dsp.sine(f, n))
            place(self.bass, x * env * 0.32, a)

    def render_pulse(self, t0, t1, every, start_gain, end_gain):
        """Soft heartbeat sub pulse (intro/tension)."""
        t = t0
        while t < t1 - 1e-6:
            g = np.interp(t, [t0, t1], [start_gain, end_gain])
            for k, (dt, gg) in enumerate(((0.0, 1.0), (0.22, 0.6))):
                n = n_of(0.5)
                tt = dsp.tvec(n)
                f = 55 + 35 * np.exp(-tt / 0.03)
                x = dsp.sine(f, n) * dsp.perc(0.5, 0.004, 0.12)
                place(self.drums, x * g * gg, t + dt)
            t += every

    def kick(self, t, g=1.0):
        n = n_of(0.45)
        tt = dsp.tvec(n)
        f = 46 + 90 * np.exp(-tt / 0.035)
        x = dsp.sine(f, n) * dsp.perc(0.45, 0.002, 0.16)
        click = dsp.fft_filter(dsp.noise(n_of(0.006), 3), lambda fr: dsp.bandpass_mag(fr, 3500, 1)) * 0.15
        x[:len(click)] += click
        place(self.drums, x * 0.55 * g, t)
        self.kicks.append(t)

    def hat(self, t, g=1.0, seed=0):
        n = n_of(0.09)
        x = dsp.fft_filter(dsp.noise(n, 100 + seed % 4), lambda f: dsp.highpass_mag(f, 7000, 2))
        x *= dsp.perc(0.09, 0.001, 0.025)
        place(self.drums, x * 0.085 * g, t, pan=0.25)

    def snare(self, t, g=1.0):
        n = n_of(0.3)
        tt = dsp.tvec(n)
        body = dsp.sine(185 + 40 * np.exp(-tt / 0.02), n) * dsp.perc(0.3, 0.001, 0.06)
        nz = dsp.fft_filter(dsp.noise(n, 9), lambda f: dsp.bandpass_mag(f, 2500, 0.7)) * dsp.perc(0.3, 0.001, 0.09)
        x = 0.5 * body + 0.35 * nz
        place(self.drums, x * 0.32 * g, t)
        place(self.music_send, x * 0.12 * g, t)

    def render_drums(self):
        L = self.length
        # four-on-the-floor sections and their hat/snare layers
        for a, b, kind in ((28, 34, "half"), (34, 64, "four"), (76, 80, "half"), (80, 84, "half"),
                           (84, 104, "four"), (104, 108, "half")):
            t = a
            while t < b - 1e-6:
                beat_in_bar = round((t % 2.0) / BEAT)
                if kind == "four" or beat_in_bar in (0, 2):
                    self.kick(t, 0.8 if kind == "half" else 1.0)
                t += BEAT
        for a, b, g in ((30, 64, 0.8), (84, 104, 1.0)):
            t = a + BEAT / 2
            i = 0
            while t < b:
                self.hat(t, g * (1.0 if i % 2 else 0.7), seed=i)
                t += BEAT / 2 if (b == 104 and t > 96) else BEAT
                i += 1
        for a, b in ((42, 52), (88, 104)):
            t = a + BEAT
            while t < b:
                self.snare(t, 0.9)
                t += 2 * BEAT
        # heartbeat pulse: intro rising, tension sparse, disagree heavy
        self.render_pulse(1.0, 8.0, 1.0, 0.15, 0.55)
        self.render_pulse(8.0, 22.0, 2.0, 0.45, 0.6)
        self.render_pulse(22.0, 28.0, 1.0, 0.4, 0.55)
        self.render_pulse(64.0, 76.0, 1.0, 0.5, 0.7)

    def render_arp(self, plan, ranges, gain=1.0):
        rng = np.random.default_rng(5)
        k = 0
        for (a, b, name) in plan:
            if not in_ranges(a, ranges):
                continue
            _, notes = CH[name]
            tones = sorted(set(m + 12 for m in notes[1:4])) + [notes[1] + 24]
            pattern = [0, 1, 2, 3, 2, 1, 2, 3]
            t = a
            i = 0
            while t < b - 1e-6:
                m = tones[pattern[i % len(pattern)] % len(tones)]
                x = dsp.additive_pluck(midi_hz(m), 0.7, bright=1.2, harmonics=16, seed=k)
                accent = 1.0 if i % 4 == 0 else 0.7
                place(self.keys, x * 0.10 * accent * gain, t, pan=-0.45 if i % 2 else 0.45)
                place(self.music_send, x * 0.05 * gain, t)
                t += BEAT / 2
                i += 1
                k += 1

    def render_lead(self, phrases):
        for t0, mel, g in phrases:
            for (off, m, beats) in mel:
                t = t0 + off * BEAT
                dur = beats * BEAT
                n = n_of(dur + 1.2)
                env = dsp.adsr(dur, 0.012, 0.5, 0.35, 1.0)[:n]
                idx = 2.2 * dsp.perc(dur + 1.2, 0.002, 0.25)[:len(env)] + 0.3
                f = midi_hz(m)
                x = dsp.fm(f, 2.0, idx, len(env)) * env * 0.6 + dsp.sine(f, len(env)) * env * 0.4
                x *= g
                place(self.lead, x * 0.085, t)
                place(self.music_send, x * 0.06, t)
                echo = dsp.ping_pong(x, 3 * BEAT / 2, fb=0.4, taps=3)
                place(self.lead, echo * 0.05, t)

    # ------------------------------------------------------------------ sfx
    def tick(self, t, f=2600, g=1.0, pan=0.0):
        n = n_of(0.06)
        x = dsp.sine(f, n) * dsp.perc(0.06, 0.0005, 0.008)
        x += 0.4 * dsp.sine(f * 2.01, n) * dsp.perc(0.06, 0.0005, 0.004)
        place(self.sfx, x * 0.22 * g, t, pan=pan)
        place(self.sfx_send, x * 0.05 * g, t, pan=pan)

    def keystroke(self, t, seed, g=1.0):
        rng = np.random.default_rng(seed)
        n = n_of(0.05)
        nz = dsp.fft_filter(dsp.noise(n, seed), lambda f: dsp.bandpass_mag(f, rng.uniform(2500, 4200), 0.8))
        x = nz * dsp.perc(0.05, 0.0004, 0.006) * 0.5
        x += dsp.sine(rng.uniform(170, 230), n) * dsp.perc(0.05, 0.001, 0.012) * 0.25  # soft thock
        place(self.sfx, x * 0.5 * g, t, pan=rng.uniform(-0.15, 0.15))

    def typing(self, t0, t1, enter_times):
        rng = np.random.default_rng(42)
        t, i = t0, 0
        while t < t1:
            self.keystroke(t, 1000 + i, g=rng.uniform(0.7, 1.0))
            t += rng.uniform(0.08, 0.17) + (0.25 if rng.random() < 0.12 else 0.0)  # word gaps
            i += 1
        for te in enter_times:
            self.keystroke(te, 77, g=1.3)
            self.tick(te + 0.03, 1760, 0.6)

    def chime(self, t, notes=(81, 88), g=1.0):
        for k, m in enumerate(notes):
            dur = 2.4
            n = n_of(dur)
            idx = 3.0 * dsp.perc(dur, 0.001, 0.15) + 0.2
            x = dsp.fm(midi_hz(m), 3.5, idx, n) * dsp.perc(dur, 0.002, 0.7)
            place(self.sfx, x * 0.06 * g, t + 0.07 * k, pan=-0.3 + 0.6 * k)
            place(self.sfx_send, x * 0.08 * g, t + 0.07 * k)

    def whoosh(self, t_peak, direction=1):
        pre, post = 0.75, 0.6
        dur = pre + post
        n = n_of(dur)
        tt = dsp.tvec(n)
        amp = np.where(tt < pre, (tt / pre) ** 2.2, np.exp(-(tt - pre) / 0.16))
        nz = dsp.noise(n, int(t_peak * 10))
        x = dsp.stft_filter(nz, lambda f, ti: dsp.bandpass_mag(
            f, np.interp(ti, [0, pre, dur], [400, 4500, 1200]), 0.9), nfft=1024, hop=256)
        x *= amp
        x /= np.max(np.abs(x)) + 1e-9
        p = np.interp(tt, [0, dur], [-0.8 * direction, 0.8 * direction])
        st = np.vstack([x * np.cos((p + 1) * np.pi / 4), x * np.sin((p + 1) * np.pi / 4)])
        place(self.sfx, st * 0.16, t_peak - pre)
        place(self.sfx_send, st * 0.08, t_peak - pre)

    def riser(self, t_end, length=3.0, g=1.0):
        n = n_of(length)
        tt = dsp.tvec(n)
        amp = (tt / length) ** 2.5
        nz = dsp.noise(n, int(t_end))
        x = dsp.stft_filter(nz, lambda f, ti: dsp.lowpass_mag(
            f, 300 * (40 ** (np.clip(ti, 0, length) / length)), 2, res=0.6), nfft=1024, hop=256)
        f = 220 * 2 ** (2 * tt / length)
        tone = 0.25 * dsp.saw(f, n)
        tone = dsp.fft_filter(tone, lambda fr: dsp.lowpass_mag(fr, 3000, 1))
        y = (x * 0.6 + tone) * amp
        y[-n_of(0.01):] *= np.linspace(1, 0, n_of(0.01))
        place(self.sfx, dsp.widen(np.vstack([y, np.roll(y, n_of(0.011))]), 1.2) * 0.07 * g, t_end - length)
        place(self.sfx_send, np.vstack([y, y]) * 0.04 * g, t_end - length)

    def impact(self, t, g=1.0):
        n = n_of(2.5)
        tt = dsp.tvec(n)
        boom = dsp.sine(30 + 50 * np.exp(-tt / 0.08), n) * dsp.perc(2.5, 0.003, 0.6)
        air = dsp.fft_filter(dsp.noise(n, 5), lambda f: dsp.lowpass_mag(f, 1800, 1)) * dsp.perc(2.5, 0.002, 0.25)
        x = boom * 0.7 + air * 0.08
        place(self.sfx, x * 0.35 * g, t)
        place(self.sfx_send, np.vstack([air, air]) * 0.06 * g, t)

    def alert(self, t, k):
        # short two-note accent (minor 2nd, softened) with a low tom underneath
        dur = 0.9
        n = n_of(dur)
        x = np.zeros(n)
        for m, d in ((76, 0.0), (77, 0.0)):
            idx = 1.5 * dsp.perc(dur, 0.001, 0.08) + 0.4
            x += dsp.fm(midi_hz(m - 2 * (k % 2)), 1.0, idx, n) * dsp.perc(dur, 0.003, 0.22)
        tom = dsp.sine(90 + 60 * np.exp(-dsp.tvec(n) / 0.04), n) * dsp.perc(dur, 0.002, 0.15)
        y = x * 0.08 + tom * 0.22
        place(self.sfx, y, t, pan=-0.2 if k % 2 else 0.2)
        place(self.sfx_send, x * 0.06, t)

    def countup(self, t0, steps=14, length=1.3, base=1500):
        # accelerating ticks rising in pitch, then a small "ding" on the final value
        u = np.linspace(0, 1, steps)
        times = t0 + length * (1 - (1 - u) ** 1.6)
        for i, ti in enumerate(times):
            self.tick(ti, base * 2 ** (i / steps * 0.8), 0.55 + 0.3 * i / steps, pan=0.1)
        self.chime(t0 + length + 0.05, notes=(86,), g=0.7)

    def resolve_sparkle(self, t):
        for i, m in enumerate((77, 81, 84, 88)):
            self.chime(t + 0.11 * i, notes=(m,), g=0.6)


def build(length: float | None = None):
    cues, end = load_cues()
    L = float(length or end)
    s = Score(L)
    plan = [(a, b, c) for a, b, c in chord_plan() if a < L]
    s.render_pads(plan)
    s.render_drone()
    s.render_bass(plan, [(22, 64), (76, 110)])
    s.render_drums()
    s.render_arp(plan, [(34, 64)], gain=1.0)
    s.render_arp(plan, [(80, 84)], gain=0.55)
    s.render_arp(plan, [(84, 108)], gain=0.9)
    s.render_lead([(34, MELODY_A, 1.0), (42, MELODY_B, 0.9), (88, MELODY_A, 1.0), (96, MELODY_B, 1.1)])
    # close: bell arpeggio over the resolve chord
    for i, m in enumerate((74, 78, 81, 86, 90)):
        s.chime(110.3 + 0.35 * i, notes=(m,), g=0.75)

    # ---- sfx from cues
    for i, t in enumerate(cues["letter_tick"]):
        s.tick(t, 2400 + 90 * i, 0.8, pan=-0.5 + i / 7)
    if len(cues.get("typing", [])) == 2:
        s.typing(cues["typing"][0], cues["typing"][1], cues.get("enter", []))
    for t in cues["chime"]:
        s.chime(t, notes=(81, 88), g=1.0)
    for i, t in enumerate(cues["whoosh"]):
        s.whoosh(t, 1 if i % 2 == 0 else -1)
    for k, t in enumerate(cues["alert"]):
        s.alert(t, k)
    for t in cues["resolve"]:
        s.resolve_sparkle(t)
    for t in cues["countup"]:
        s.countup(t)
    for t in cues["impact"]:
        s.impact(t, 1.0 if t != 110 else 0.8)
    for t_end, ln in ((8, 3.0), (34, 3.0), (52, 1.5), (64, 2.0), (96, 3.5)):
        s.riser(t_end, ln, 0.8 if t_end in (52, 64) else 1.0)

    # ---- mix buses
    N = s.N
    duck_pad = dsp.duck_curve(N, s.kicks, 0.30)
    duck_bass = dsp.duck_curve(N, s.kicks, 0.65, release=0.12)
    ir_music = dsp.make_ir(t60=2.6, seed=7)
    ir_sfx = dsp.make_ir(t60=1.6, seed=8, bright=10000)
    music_wet = dsp.reverb(s.music_send, ir_music) * 0.55
    music = (s.pad * duck_pad + s.bass * duck_bass + s.drums + s.keys * (0.6 + 0.4 * duck_pad)
             + s.lead + music_wet * (0.7 + 0.3 * duck_pad))
    sfx = s.sfx + dsp.reverb(s.sfx_send, ir_sfx) * 0.5

    # global shaping: rumble filter, gentle fades
    # rumble filter + gentle air shelf (+2.5 dB above ~7 kHz)
    music = dsp.fft_filter(music, lambda f: dsp.highpass_mag(f, 28, 2)
                           * (1 + 0.33 * dsp.highpass_mag(f, 7000, 1)))
    fade = dsp.ramp_curve(N, [(0, 0.0), (0.25, 1.0), (L - 4.5, 1.0), (L - 0.05, 0.0), (L, 0.0)]) ** 1.5
    music *= fade
    sfx *= dsp.ramp_curve(N, [(0, 1.0), (L - 3.0, 1.0), (L - 0.05, 0.0), (L, 0.0)])
    used = {k: v for k, v in cues.items()}
    used["kicks"] = s.kicks
    return music, sfx, used
