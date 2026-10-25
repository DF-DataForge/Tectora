# Video pipeline — explainer videos from the scripts

Turns a script in `docs/video_scripts/` into a finished video: Playwright
clicks through a demo database, Piper speaks the voice-over in Flemish, and
ffmpeg puts it together with captions, brand cards, subtitles and a
thumbnail. Re-running it after an Odoo or module change gives a fresh video.

```
script (.md)  ─┬─ Voice-over ──────► Piper ─► one WAV per shot ─┐
               └─ Tekst in beeld ─┐                              ├─► ffmpeg ─► .mp4 .srt .jpg
storyboard (.yaml) ─► Playwright ─┴─► Odoo on Xvfb ─► raw.mkv ───┘
```

* **Script** (`docs/video_scripts/**.md`): what is *said* and the text
  shown on screen. It stays the only place to edit the text.
* **Storyboard** (`storyboards/*.yaml`): what the browser *does* per shot.

## Setup (once)

Linux (or WSL) with `ffmpeg` and `Xvfb`:

```bash
python3 -m venv .venv-video
.venv-video/bin/pip install -r tools/video_pipeline/requirements.txt
.venv-video/bin/playwright install chromium
```

The Piper voice (`nl_BE-nathalie-medium`, or `nl_BE-rdh-medium` for a male
voice) is downloaded on first use to `~/.cache/tectora-video/voices`.

A **demo database**, never production: Odoo 20 with `tectora_roof`,
`tectora_products`, `tectora_report_layout` and `sale_stock`, language
Dutch (BE). Load the demo case (Familie Peeters) with:

```bash
odoo shell -c odoo.conf -d tectora_demo < tools/video_pipeline/seed_demo.py
```

The seed is idempotent and removes what an earlier take created, so pass
it as `--reset` and every take starts from the same screen.

## Making a video

```bash
# 1. Rehearse: headless, no recording; fails fast with error.png on a missing button
.venv-video/bin/python tools/video_pipeline/make_video.py \
    tools/video_pipeline/storyboards/dakmeting_02_dakproject_starten.yaml --capture none

# 2. Record
ODOO_PASSWORD=... .venv-video/bin/python tools/video_pipeline/make_video.py \
    tools/video_pipeline/storyboards/dakmeting_02_dakproject_starten.yaml \
    --url http://localhost:8069 --login admin \
    --reset "odoo shell -c odoo.conf -d tectora_demo < tools/video_pipeline/seed_demo.py" \
    --music muziek.mp3   # optional, ducks under the voice
```

Output in `build/videos/<storyboard>/`: `<name>.mp4` (1080p30, H.264/AAC),
`<name>.srt` (subtitles from the voice-over), `<name>.jpg` (thumbnail) and
`timeline.json`. `--voice-only` only synthesises the voice-over and prints
the length per shot against the script.

## Writing a storyboard

Shot numbers follow the script table. Per shot either a `card` or `steps`:

```yaml
script: docs/video_scripts/dakmeting/02_dakproject_starten.md
series: Tectora Dakmeting     # subtitle on the cards
voice: nl_BE-nathalie-medium
tempo: 1.15                   # >1 slower; 1.15 ≈ the scripts' 130 words/min
start: /odoo/crm              # screen under the opening card
pronunciation: {CRM: C R M}   # audio only
shots:
  1: {card: title}            # brand card with the shot's "Tekst in beeld"
  3:
    setup: [...]              # runs at the end of the previous shot (behind its card)
    steps:
      - app: CRM                              # via the app menu
      - menu: Dakprojecten                    # top menu
      - click: Renovatie plat dak Peeters     # button/link/tab/text
      - click: {button: Dakproject maken}     # or {selector: css}, {field: name}
      - fill: {field: partner_id, value: Peeters, pick: Familie Peeters}
      - save:
      - highlight: {field: address, seconds: 2}
      - zoom: {selector: .o_statusbar_status, scale: 2}
      - wait: 1.5
```

Each shot shows its caption, runs its steps while the voice speaks, and holds
until the voice-over is done; so the voice decides the length, as the
scripts intend. A card's `kind: html` takes free HTML (see the diagram in
shot 2 of the example).

## Publishing

Upload the MP4 (unlisted on YouTube/Vimeo, or Google Drive) and add it as
*Video* content to the course in Odoo eLearning; the `.srt` goes along as
subtitles on YouTube/Vimeo.

## Limits of this proof of concept

* Only `dakmeting_02` has a storyboard; the other 20 scripts need one each.
  Drawing on the canvas (Dakmeting 03/04) needs mouse-path steps that do
  not exist yet.
* Piper is free and offline but sounds synthetic; a paid voice (e.g.
  ElevenLabs) would slot in next to `tts.PiperVoice`.
* `--capture playwright` works on macOS/Windows without Xvfb, but the image
  is softer.
