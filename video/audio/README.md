# Audio for the Second Eye video

All sound is generated from code (Python 3 + numpy + ffmpeg). It uses no samples, downloads or copyrighted material.
Timings come from `video/storyboard.json`, the timeline shared with `video/remotion/`.

```bash
python3 -m video.audio.build                # -> video/out/audio/{music,sfx,mix}.wav, cues.json, stats.json
python3 -m video.audio.script               # regenerate captions.srt + narration.md from script.py
video/audio/make_voice.sh                   # macOS: say -> voice.wav, then build --with-voice
python3 -m video.audio.build --with-voice   # mix voice.wav on top; the music ducks about 9 dB under speech
python3 -m video.qa.check                   # QA the rendered video (see video/qa/)
```

Remotion muxes `video/out/audio/mix.wav` when that file exists. Everything in `video/out/` is gitignored.

## Files
| File | What it does |
|---|---|
| `dsp.py` | Synth and mix toolkit: PolyBLEP saw, FM, additive plucks, ADSR, FFT and STFT (time-varying) filters, synthetic stereo IR and convolution reverb, ping-pong delay, M/S width, sidechain duck curves, look-ahead limiter, WAV I/O, ffmpeg `ebur128` metering |
| `score.py` | The arrangement and sound design. Cue times are in `DEFAULT_CUES` |
| `build.py` | Renders the stems and masters `mix.wav` to -14 LUFS integrated with true peak ≤ -1.2 dBTP (measure, adjust gain, limit, repeat). Prints loudness and spectral statistics for each scene |
| `script.py` | The voice-over text (single source) and its timing: it writes `captions.srt` and `narration.md` and checks pace (≤ 2.3 words/s) |
| `voice.py`, `make_voice.sh` | Text-to-speech for each caption cue with macOS `say` (Samantha, fallback Daniel). Each line is placed at its cue start and sped up with atempo (max 1.25x) if it overruns. `--fake` writes a speech-like placeholder for testing on Linux |

## Music (120 BPM, D minor, bar = 2 s, every scene starts on a bar line)
| Scene | Music | SFX (default cue times, s) |
|---|---|---|
| hook 0-8 | Dm9 pad whose filter opens, heartbeat sub pulse rising | riser into 8 |
| problem 8-22 | dark drone, dissonant shimmer, sparse pulse | letter tick ×8 (9.0 … 17.75) |
| ask 22-34 | Dm9-Bb-Gm-A, sub bass, kick enters at 28, hats at 30 | typing 23.0-28.6, enter 29.0, riser into 34 |
| screen 34-52 | main theme: Dm-Bb-F-C, plucked arpeggio, FM lead, full groove | impact 34, chime 44.0 |
| switch 52-64 | theme variation (Gm-Bb-F-C) | whoosh 55.0, 59.5 |
| disagree 64-80 | drums drop, drone and heartbeat, Bb-Gm-Eb-A7 tension → Fmaj9 resolve at 76 | alert 66/68/70/72/74, resolve sparkle 76 |
| how 80-96 | steady build: arpeggio, kick, hats, snare, lead, riser | riser into 96 |
| results 96-110 | full theme, then strips back at 104 for "what doesn't work yet" | impact 96, count-up 97/99/101/103 |
| close 110-118 | D major add9 (Picardy resolve), bell arpeggio, fade to 118 | impact 110 |

To sync SFX to the final animation, add optional `"cues"` to a storyboard scene, for example
`{"id": "switch", ..., "cues": {"whoosh": [55.2, 59.8]}}`. Keys: `letter_tick, typing ([start,end]), enter, chime, whoosh, alert, resolve, countup, impact`.
The times actually used are written to `video/out/audio/cues.json`.

## Checking by numbers instead of listening
`build.py` prints, for each scene, the RMS and peak level, the spectral centroid and the share of energy in each band. `stats.json` keeps the same figures.
`python3 -m video.qa.check` renders a waveform and a spectrogram. The values measured at the last build (no voice) were I = -14.0 LUFS, TP = -1.6 dBTP and LRA 4.7 LU.
The loud scenes (screen to results) sit at about -14.5 dBFS RMS. Hook, problem and disagree are 2 to 7 dB quieter by design. Most of the energy is below 2 kHz, which leaves room for the voice.

## Voice-over
No text-to-speech voices can be downloaded in the cloud sandbox, so the voice is made on a Mac:
1. `video/audio/make_voice.sh` (change the voice with `VOICE=Daniel`, the speed with `RATE=160`). It prints the length of each line and flags any line that is too long.
2. That script runs `python3 -m video.audio.build --with-voice` itself, which rewrites `mix.wav` with the voice and ducks the music under it. Re-render the video afterwards.
3. Rerun `python3 -m video.qa.check`. Burn in `captions.srt` or upload it as subtitles.

If you change the script text, edit `script.py`, run `python3 -m video.audio.script`, and redo the voice.
The spoken numbers (15 of 15, five contradictions, zero invented, 100 % linked) must match `video/metrics.json`. The QA check compares them.
