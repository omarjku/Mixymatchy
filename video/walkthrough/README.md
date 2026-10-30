# 30 s vertical walkthrough (9:16)

A 30 s, 1080x1920, 30 fps product walkthrough of the mobile app, drawn in code. Output:
`docs/media/second-eye-walkthrough-9x16.mp4`.

```
walkthrough.html   the whole animation; every frame is render(t). Open with ?play to preview in a browser.
render.mjs         renders 900 frames with Playwright and pipes them to ffmpeg (muxes audio.wav)
audio.py           ambient pad + a UI click at each tap (tap times match TAPS in walkthrough.html)
```

```bash
(cd mobile && npm ci)                              # IBM Plex Sans (@fontsource) and Playwright
python3 video/walkthrough/audio.py                 # video/out/walkthrough/audio.wav
node video/walkthrough/render.mjs                  # video/out/walkthrough/second-eye-walkthrough.mp4
node video/walkthrough/render.mjs stills 5 12 18   # PNG stills at those seconds
```

| Time | Scene | Caption |
|---|---|---|
| 0–4 s | Start screen, empty field | One question. Any wording. |
| 4–9 s | Tap, question types itself, "Show answer", timer stops at 2.1 s | Reads all 8 letters. |
| 9–15 s | Answer card; "not documented" pulses amber; chips [1] [2] | One sentence. Only what matters. |
| 15–21 s | Tap [1]; letter slides in, scrolls, marker on "Glucophage 1000 mg 1-1-1" | Every fact proven in the source. |
| 21–27 s | Back; "Show more"; details with the "Letters disagree" badge | Details and contradictions, one tap away. |
| 27–30 s | End card with logo and tagline | |

The only patient text is the scripted text above; the rest of the letter is drawn as grey placeholder lines.
