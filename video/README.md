# Submission video (code-rendered)

A 118 s, 1920x1080, 30 fps video rendered with [Remotion](https://www.remotion.dev) from code. No footage is
typed in by hand: every number and label on screen comes from the running system.

```
video/storyboard.json        scene ids + timings (shared contract with the audio in video/audio/)
video/scripts/export_metrics.py   runs engine/ compare/ eval/ (via backend/app/adapter.py) -> video/metrics.json
video/scripts/capture_app.mjs     runs the real app (uvicorn + static frontend) in Playwright -> remotion/public/capture/
video/scripts/render.mjs          stills + contact sheet, or the MP4 (muxes video/out/audio/mix.wav if present)
video/scripts/check_visual.mjs    layout / black-frame / duration checks
video/remotion/src/               the composition (Root.tsx) and one file per scene (scenes/*.tsx)
```

`video/metrics.json`, `video/out/`, the captures and `remotion/src/generated/` are git-ignored: they contain
labels and screenshots derived from the patient letters. The code contains no letter text.

## Render

Needs the organisers' data in `data/` (see the main README), Python 3.11+, Node 20+, ffmpeg.

```bash
pip install -r backend/requirements.txt
(cd frontend && npm ci)
cd video/remotion && npm ci

npm run metrics      # python3 ../scripts/export_metrics.py  -> video/metrics.json (15/15, latency over HTTP, ...)
npm run capture      # node ../scripts/capture_app.mjs     -> builds frontend (STATIC_EXPORT=1), screenshots the app
npm run stills       # video/out/stills/NN-<scene>.png + video/out/contact_sheet.png
npm run check        # video/out/check_report.json; exits 1 on a problem
npm run render       # video/out/second-look.mp4
npm run studio       # live preview / scrubbing (run `npm run stills` once first: it prepares src/generated/)
```

- Audio: `python3 -m video.audio.build` (repo root) writes `video/out/audio/mix.wav`; `npm run render` muxes
  it in automatically, otherwise the MP4 is silent.
- Browser: Remotion's own headless shell is used if it can be downloaded; otherwise the scripts pick a local
  Chromium (`/opt/pw-browsers/...`) or `REMOTION_BROWSER=/path/to/chrome`.
- Without captures the screen/switch scenes fall back to card lists drawn from `metrics.json`.
- `export_metrics.py --root=<checkout>` runs another checkout (e.g. a clean `git archive HEAD`) while the
  working tree is mid-edit; `--no-http` skips the uvicorn latency run.
- One scene only: `node ../scripts/render.mjs stills screen`.

## What the checks mean

`npm run check` renders probe frames with `inputProps {check: true}`; `src/components/Probe.tsx` measures every
visible text run in the DOM and reports text outside the 5 % title-safe area or cut off by an
`overflow: hidden` box. It also samples one frame per second for fully black frames (only the final fade of
`close` may be black), and checks that the composition length equals the storyboard (and the MP4 length, if
rendered). The contact sheet is the quickest human check: one settled key frame per scene.

## Edit scenes

- Timing: change `video/storyboard.json` only (the audio follows the same file). Scene components get their
  length as `dur` and place animations relative to it or to fixed frames inside the scene.
- A scene is `src/scenes/<Name>.tsx`, registered by storyboard id in `SCENES` in `src/Root.tsx`.
- Design tokens (palette, fonts, safe area) are in `src/theme.ts`; motion helpers (`tween`, `spr`, `keys`)
  in `src/lib.ts`; kinetic type (`Words`, `Rise`, `Kicker`, `Count`) in `src/components/Text.tsx`.
- Data: `M` (metrics) and `SB` (storyboard) from `src/data.ts`. Need a new number? Add it to
  `export_metrics.py`, never type it into a scene.
- Camera moves on captures: `ShotView` takes a focus point in page pixels (1440-wide capture) and a zoom; the
  element boxes in `public/capture/manifest.json` (written by `capture_app.mjs`) give the targets.
- Key frame of each scene for the stills: `STILL_AT` in `video/scripts/common.mjs`.
- "What does not work yet" comes from `docs/HANDOFF.md` section 8 (see `NOT_YET` in `export_metrics.py`):
  a line is only shown while the handoff still lists that item.
