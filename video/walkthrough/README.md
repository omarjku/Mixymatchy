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
| 0–3 s | Start screen, Second Eye logo, empty field | One question. Any wording. |
| 3–7.5 s | Tap, question types itself, "Show answer", timer stops at 2.1 s | Reads all 8 letters. |
| 7.5–11.6 s | Answer card; "not documented" pulses amber; chips [1] [2] | One sentence. Only what matters. |
| 11.6–16.6 s | Tap [1]; the whole letter slides in, "Glucophage 1000 mg 1-1-1" is marked, English line below | Every fact proven in the source. |
| 16.6–20.6 s | Back; "Show more"; details with Verified / Not documented / "Letters disagree" | Details and contradictions, one tap away. |
| 20.6–24.4 s | Dashboard tab: proof ring 100 %, reliability bar 3/1/1, tiles 8 letters · 2 sources · 2.1 s | Statistics and charts at a glance. |
| 24.4–27.9 s | Results: 15/15, 100 % linked, 0 invented, 5 contradictions, 144 ms (docs/SUBMISSION.md §1) | Measured on the 5 test situations. |
| 27.9–30 s | End card: logo and tagline | |

Patient text is only the scripted facts. The source letter is an invented demo letter ("fiktive Testperson") built
from those same facts; it is not one of the organisers' documents. Dashboard numbers are counted from the five
detail rows; results numbers are the measured ones in `docs/SUBMISSION.md` section 1.

## Prompt (for a generative video tool)

```
Create a 30-second, 9:16 vertical product walkthrough of a mobile clinical app called "Second Eye". Logo: a
periwinkle (#6381fd) rounded square with a white hand presenting the letters "SE" on a platter. Dark navy
background (#0f1222), white text, indigo primary button (#4f5bea), teal accents (#2dd4bf), IBM Plex Sans.
Calm, precise motion: 250–400 ms eased transitions, no bouncing. Captions at the top in white, max 6 words.
Subtle click per tap, soft ambient pad. No voice-over.

0–3 s: Start screen: logo, title "Second Eye", empty field "Who are you and what do you need?". Caption "One question. Any wording."
3–7.5 s: Finger taps the field; text types: "Emergency doctor, I'm about to give IV gentamicin." Tap "Show answer";
corner timer counts and stops at "2.1 s". Caption "Reads all 8 letters."
7.5–11.6 s: Answer card slides up: "Kidney function (creatinine, eGFR) is not documented in the 8 letters; she has
type 2 diabetes and takes metformin 1000 mg 1-1-1." Chips [1] [2]; "not documented" pulses amber once.
Caption "One sentence. Only what matters."
11.6–16.6 s: Tap [1]. A full German discharge letter page ("Entlassbrief") slides in from the right: greeting,
Diagnosen (Diabetes mellitus Typ 2, Karotisstenose links), Allergien (Kontrastmittelallergie), Medikation bei
Entlassung, Procedere, closing. A yellow marker sweeps "Glucophage 1000 mg 1-1-1"; below it
"English: metformin 1000 mg, morning, noon and evening". Caption "Every fact proven in the source."
16.6–20.6 s: Back; tap "Show more": Metformin 1000 mg 1-1-1 (Verified), Type 2 diabetes (Verified), Contrast media
allergy (Verified), Kidney function (Not documented, amber), red "Letters disagree" badge "Carotid stenosis: left vs
right". Caption "Details and contradictions, one tap away."
20.6–24.4 s: Tap the "Dashboard" tab: a ring fills to 100% "Facts linked to their source, 4 of 4 documented facts";
a stacked bar "3 verified · 1 letters disagree · 1 not documented"; three tiles count up: 8 letters read,
2 sources cited, 2.1 s to answer. Caption "Statistics and charts at a glance."
24.4–27.9 s: Results screen "5 official test situations, 15 questions", bars grow: Correct answers 15/15,
Facts linked to their source 100%, Invented facts 0, Contradictions found 5 (target 5 or more, 0 false alarms),
Slowest screen 144 ms (target under 10 s). Caption "Measured on the 5 test situations."
27.9–30 s: Fade to the logo, "Second Eye", "Other tools summarise the record. Second Eye checks it." Hold 1 s.

Rules: show only the text above; no other patient data, numbers or drug names; no real hospital names or logos;
all UI text legible on a phone.
```
