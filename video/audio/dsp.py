"""Small numpy-only DSP toolkit for the procedural soundtrack.

Everything is vectorised (no per-sample Python loops) so a 2-minute stereo
48 kHz render takes seconds. Signals are float64; stereo buses are (2, N).
"""
from __future__ import annotations

import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

SR = 48000


# --------------------------------------------------------------------------- basics
def midi_hz(m):
    return 440.0 * 2.0 ** ((np.asarray(m, dtype=float) - 69.0) / 12.0)


def db(x):
    return 20.0 * np.log10(np.maximum(np.abs(x), 1e-12))


def undb(d):
    return 10.0 ** (np.asarray(d, dtype=float) / 20.0)


def n_of(seconds: float) -> int:
    return int(round(seconds * SR))


def tvec(n: int) -> np.ndarray:
    return np.arange(n) / SR


def pan_gains(pan: float):
    """Equal-power pan, pan in [-1, 1]."""
    a = (pan + 1.0) * np.pi / 4.0
    return np.cos(a), np.sin(a)


def place(bus: np.ndarray, x: np.ndarray, t: float, pan: float = 0.0, gain: float = 1.0):
    """Add mono (N,) or stereo (2, N) signal x into bus at time t (seconds)."""
    i0 = n_of(t)
    if x.ndim == 1:
        gl, gr = pan_gains(pan)
        x = np.vstack([x * gl, x * gr])
    n = x.shape[1]
    j0, j1 = max(i0, 0), min(i0 + n, bus.shape[1])
    if j1 <= j0:
        return
    bus[:, j0:j1] += gain * x[:, j0 - i0:j1 - i0]


# --------------------------------------------------------------------------- envelopes
def adsr(gate: float, a: float, d: float, s: float, r: float) -> np.ndarray:
    """Linear-attack, exponential decay/release ADSR. Length gate + r seconds."""
    n_g, n_r = max(n_of(gate), 1), n_of(r)
    t = tvec(n_g)
    a = max(a, 1e-4)
    env = np.where(t < a, t / a, s + (1 - s) * np.exp(-(t - a) / max(d, 1e-4) * 3.0))
    # smooth attack corner (raised cosine) to avoid clicks
    att = t < a
    env[att] = 0.5 - 0.5 * np.cos(np.pi * t[att] / a)
    last = env[-1]
    rel = last * np.exp(-tvec(n_r) / max(r, 1e-4) * 5.0) if n_r else np.zeros(0)
    if n_r:
        rel *= np.linspace(1, 0, n_r) ** 0.5  # make sure it reaches exactly zero
    return np.concatenate([env, rel])


def perc(dur: float, attack: float = 0.002, decay: float = 0.2) -> np.ndarray:
    n = n_of(dur)
    t = tvec(n)
    env = np.exp(-t / decay)
    na = max(n_of(attack), 1)
    env[:na] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(na) / na)
    fade = min(n, n_of(0.01))
    env[n - fade:] *= np.linspace(1, 0, fade)
    return env


def ramp_curve(n: int, points: list[tuple[float, float]]) -> np.ndarray:
    """Piecewise-linear automation over n samples from (time, value) points."""
    ts, vs = zip(*points)
    return np.interp(tvec(n), ts, vs)


# --------------------------------------------------------------------------- oscillators
def phase_of(freq, n: int, phase0: float = 0.0) -> np.ndarray:
    f = np.broadcast_to(np.asarray(freq, dtype=float), (n,))
    dt = f / SR
    return (phase0 + np.cumsum(dt) - dt[0]) % 1.0


def sine(freq, n: int, phase0: float = 0.0) -> np.ndarray:
    return np.sin(2 * np.pi * phase_of(freq, n, phase0))


def saw(freq, n: int, phase0: float = 0.0) -> np.ndarray:
    """PolyBLEP band-limited sawtooth."""
    f = np.broadcast_to(np.asarray(freq, dtype=float), (n,))
    dt = f / SR
    ph = (phase0 + np.cumsum(dt) - dt[0]) % 1.0
    y = 2 * ph - 1
    m1 = ph < dt
    t = ph[m1] / dt[m1]
    y[m1] -= t + t - t * t - 1
    m2 = ph > 1 - dt
    t = (ph[m2] - 1) / dt[m2]
    y[m2] -= t * t + t + t + 1
    return y


def fm(fc, ratio: float, index_env, n: int) -> np.ndarray:
    """Two-operator FM (phase modulation)."""
    mod = sine(np.asarray(fc) * ratio, n)
    return np.sin(2 * np.pi * phase_of(fc, n) + index_env * mod)


def additive_pluck(f: float, dur: float, bright: float = 1.0, harmonics: int = 24,
                   seed: int = 0) -> np.ndarray:
    """Plucked string-like tone: harmonics decaying faster the higher they are."""
    n = n_of(dur)
    t = tvec(n)
    rng = np.random.default_rng(seed)
    y = np.zeros(n)
    for k in range(1, harmonics + 1):
        fk = f * k * (1 + 0.0004 * k * k)  # slight inharmonicity
        if fk > SR * 0.45:
            break
        amp = (1.0 / k) * np.exp(-(k - 1) / (6.0 * bright))
        dec = 0.9 / (1 + 0.35 * k / bright)
        y += amp * np.exp(-t / dec) * np.sin(2 * np.pi * fk * t + rng.uniform(0, 2 * np.pi))
    na = n_of(0.003)
    y[:na] *= np.linspace(0, 1, na)
    y[-n_of(0.02):] *= np.linspace(1, 0, n_of(0.02))
    return y


def noise(n: int, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).standard_normal(n)


# --------------------------------------------------------------------------- filters
def lowpass_mag(f, fc, order: int = 2, res: float = 0.0):
    fc = np.maximum(fc, 10.0)
    g = 1.0 / np.sqrt(1.0 + (f / fc) ** (2 * order))
    if res:
        g = g * (1.0 + res * np.exp(-(np.log2(np.maximum(f, 1.0) / fc) ** 2) / (2 * 0.18 ** 2)))
    return g


def highpass_mag(f, fc, order: int = 2):
    fc = np.maximum(fc, 1.0)
    r = (np.maximum(f, 1e-3) / fc) ** (2 * order)
    return np.sqrt(r / (1.0 + r))


def bandpass_mag(f, fc, q: float = 1.0):
    """Gaussian band on log-frequency; q ~ octaves^-1."""
    return np.exp(-(np.log2(np.maximum(f, 1.0) / np.maximum(fc, 1.0)) ** 2) * q * q * 2.0)


def fft_filter(x: np.ndarray, gain_fn) -> np.ndarray:
    """Static zero-phase filter: gain_fn(freqs) -> magnitude."""
    if x.ndim == 2:
        return np.vstack([fft_filter(c, gain_fn) for c in x])
    n = len(x)
    pad = min(n, SR // 2)
    xp = np.concatenate([x, np.zeros(pad)])
    X = np.fft.rfft(xp)
    X *= gain_fn(np.fft.rfftfreq(len(xp), 1 / SR))
    return np.fft.irfft(X, len(xp))[:n]


def stft_filter(x: np.ndarray, gain_fn, nfft: int = 2048, hop: int = 512,
                chunk: int = 256) -> np.ndarray:
    """Time-varying zero-phase filter. gain_fn(freqs[None,:], times[:,None]) -> (frames, bins)."""
    if x.ndim == 2:
        return np.vstack([stft_filter(c, gain_fn, nfft, hop, chunk) for c in x])
    n = len(x)
    xp = np.concatenate([np.zeros(nfft), x, np.zeros(nfft + hop)])
    nfr = 1 + (len(xp) - nfft) // hop
    win = np.hanning(nfft + 1)[:-1]
    freqs = np.fft.rfftfreq(nfft, 1 / SR)[None, :]
    frames = np.lib.stride_tricks.sliding_window_view(xp, nfft)[::hop]
    out = np.zeros(len(xp))
    for c0 in range(0, nfr, chunk):
        fr = frames[c0:c0 + chunk] * win
        starts = (np.arange(c0, c0 + len(fr)) * hop)
        times = ((starts + nfft / 2 - nfft) / SR)[:, None]
        Y = np.fft.rfft(fr, axis=1) * gain_fn(freqs, times)
        y = np.fft.irfft(Y, nfft, axis=1) * win
        for i, s in enumerate(starts):
            out[s:s + nfft] += y[i]
    return out[nfft:nfft + n] / 1.5  # Hann^2 at 75 % overlap sums to 1.5


# --------------------------------------------------------------------------- space
def convolve(x: np.ndarray, h: np.ndarray) -> np.ndarray:
    n = len(x) + len(h) - 1
    N = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, N) * np.fft.rfft(h, N), N)[:len(x)]


def make_ir(t60: float = 2.4, predelay: float = 0.02, seed: int = 7,
            bright: float = 8000.0) -> np.ndarray:
    """Synthetic stereo room/hall impulse response (2, N): early reflections +
    decorrelated exponentially decaying noise whose high end dies faster."""
    n = n_of(t60 * 1.15)
    t = tvec(n)
    rng = np.random.default_rng(seed)
    ir = np.zeros((2, n))
    for c in range(2):
        tail = rng.standard_normal(n) * np.exp(-6.9 * t / t60)
        tail *= 1 - np.exp(-t / 0.015)  # soft onset of the diffuse field
        tail = stft_filter(tail, lambda f, tt: lowpass_mag(f, bright * np.exp(-tt / (t60 * 0.35)) + 900, 1),
                           nfft=1024, hop=256)
        tail = fft_filter(tail, lambda f: highpass_mag(f, 120, 1))
        er = np.zeros(n)
        for _ in range(14):
            k = n_of(rng.uniform(0.004, 0.075))
            er[k] += rng.choice([-1, 1]) * rng.uniform(0.15, 0.6) * np.exp(-k / SR / 0.05)
        ir[c] = tail / np.sqrt(np.sum(tail ** 2)) + 0.6 * er
    pre = np.zeros((2, n_of(predelay)))
    ir = np.hstack([pre, ir])
    return ir / np.sqrt(np.mean(np.sum(ir ** 2, axis=1)))


def reverb(send: np.ndarray, ir: np.ndarray) -> np.ndarray:
    """Stereo in (2,N): L->IR_L, R->IR_R plus a little cross-feed for width."""
    l = convolve(send[0], ir[0])
    r = convolve(send[1], ir[1])
    return np.vstack([0.85 * l + 0.15 * r, 0.85 * r + 0.15 * l])


def widen(x: np.ndarray, width: float) -> np.ndarray:
    m = 0.5 * (x[0] + x[1])
    s = 0.5 * (x[0] - x[1]) * width
    return np.vstack([m + s, m - s])


def ping_pong(x: np.ndarray, delay: float, fb: float = 0.45, taps: int = 5) -> np.ndarray:
    """Finite ping-pong echo of a mono/stereo signal (taps darken progressively)."""
    mono = x if x.ndim == 1 else 0.5 * (x[0] + x[1])
    out = np.zeros((2, len(mono)))
    d = n_of(delay)
    cur = mono
    for k in range(1, taps + 1):
        cur = fft_filter(cur, lambda f: lowpass_mag(f, 5000, 1))
        if k * d >= len(mono):
            break
        out[k % 2, k * d:] += (fb ** k) * cur[:len(mono) - k * d]
    return out


# --------------------------------------------------------------------------- dynamics
def running_min(x: np.ndarray, w: int) -> np.ndarray:
    """m[i] = min(x[i:i+w]) for i in range(len(x)-w+1) (van Herk / Gil-Werman)."""
    n = len(x)
    out_n = n - w + 1
    total = ((n + w - 1) // w + 1) * w
    xp = np.full(total, np.inf)
    xp[:n] = x
    b = xp.reshape(-1, w)
    pre = np.minimum.accumulate(b, axis=1).ravel()
    suf = np.minimum.accumulate(b[:, ::-1], axis=1)[:, ::-1].ravel()
    i = np.arange(out_n)
    return np.minimum(suf[i], pre[i + w - 1])


def box(x: np.ndarray, w: int) -> np.ndarray:
    """Centered moving average with odd window w (edges use available samples)."""
    h = w // 2
    xp = np.concatenate([np.full(h, x[0]), x, np.full(h, x[-1])])
    c = np.concatenate([[0.0], np.cumsum(xp)])
    return (c[w:] - c[:-w]) / w


def limiter(x: np.ndarray, ceiling_db: float = -1.5, look: float = 0.004,
            release_db_per_s: float = 30.0) -> tuple[np.ndarray, np.ndarray]:
    """Look-ahead brickwall limiter. Returns (output, gain curve in dB)."""
    c = undb(ceiling_db)
    peak = np.max(np.abs(x), axis=0)
    req = np.minimum(1.0, c / np.maximum(peak, 1e-9))
    L = max(n_of(look), 2)
    m = running_min(np.pad(req, (L - 1, L - 1), constant_values=1.0), 2 * L - 1)
    g = np.minimum(box(m, 2 * L - 1), req)
    gd = db(g)
    r = release_db_per_s / SR
    idx = np.arange(len(gd))
    grel = np.minimum(gd, r * idx + np.minimum.accumulate(gd - r * idx))
    y = x * undb(grel)
    return np.clip(y, -c, c), grel


def duck_curve(n: int, times, depth: float, attack: float = 0.008,
               release: float = 0.16) -> np.ndarray:
    """Sidechain-style gain curve (1 = no ducking) triggered at given times."""
    shape_n = n_of(attack + release * 5)
    t = tvec(shape_n)
    shape = np.where(t < attack, t / attack, np.exp(-(t - attack) / release))
    act = np.zeros(n)
    for tk in times:
        i0 = n_of(tk) - n_of(attack)
        j0, j1 = max(i0, 0), min(i0 + shape_n, n)
        if j1 > j0:
            np.maximum(act[j0:j1], shape[j0 - i0:j1 - i0], out=act[j0:j1])
    return 1.0 - depth * act


def envelope_follow(x: np.ndarray, win: float = 0.05) -> np.ndarray:
    mono = x if x.ndim == 1 else np.max(np.abs(x), axis=0)
    w = n_of(win) | 1
    return np.sqrt(box(mono ** 2, w))


# --------------------------------------------------------------------------- I/O + metering
def write_wav(path: Path, x: np.ndarray, bits: int = 24):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    x = np.atleast_2d(x)
    inter = np.clip(x.T, -1.0, 1.0)
    if bits == 24:
        i = np.round(inter * 8388607.0).astype("<i4").ravel()
        data = i.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
    else:
        rng = np.random.default_rng(1)
        tpdf = (rng.random(inter.shape) - rng.random(inter.shape)) / 32768.0
        data = np.clip(np.round((inter + tpdf) * 32767.0), -32768, 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(x.shape[0])
        w.setsampwidth(bits // 8)
        w.setframerate(SR)
        w.writeframes(data)


def read_wav(path: Path) -> np.ndarray:
    """Read any audio file via ffmpeg into (2, N) float64 at SR."""
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2",
                          "-ar", str(SR), "-"], capture_output=True, check=True).stdout
    return np.frombuffer(out, dtype="<f4").reshape(-1, 2).T.astype(np.float64)


def ebur128(path: Path) -> dict:
    """Integrated loudness, LRA and true peak via ffmpeg's ebur128 filter."""
    p = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-i", str(path), "-filter_complex",
                        "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    txt = p.stderr[p.stderr.rfind("Summary:"):]
    res = {}
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith("I:"):
            res["I"] = float(s.split()[1])
        elif s.startswith("LRA:"):
            res["LRA"] = float(s.split()[1])
        elif s.startswith("Peak:"):
            res["TP"] = float(s.split()[1])
    return res


def measure(x: np.ndarray) -> dict:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "m.wav"
        write_wav(p, x)
        return ebur128(p)
