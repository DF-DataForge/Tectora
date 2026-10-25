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

A **demo database**, never production: Odoo 20 with all Tectora modules
except `tectora_roof_planning` (Planning is Enterprise), plus `calendar`,
`hr_timesheet` and `l10n_be` with the Belgian chart (for 6 % VAT), language
Dutch (BE). Also needed on the machine:

* **wkhtmltopdf 0.12.6.1 with patched Qt** (the `wkhtmltox` package from the
  wkhtmltopdf project, not Ubuntu's) — Odoo refuses the unpatched one for
  quotations. Restart Odoo after installing it.
* **A mail sink on localhost:25** (e.g. `python -m aiosmtpd -n -l
  127.0.0.1:25 -c aiosmtpd.handlers.Sink`), so mails Odoo sends during a
  take succeed instead of showing up as failed-mail counters.

The demo case (Tectora, client Peeters with salutation Familie) comes from
`seed_demo.py`, one **stage** per point in the story (`lead_new`, `lead`,
`lead_notes`, `quote`, `quote_norecalc`, `project`, `timer`; see its
docstring). A storyboard names its `stage`; `make_video.py` passes it to the
`--reset` command as `$VIDEO_STAGE` (and the assets folder as
`$VIDEO_ASSETS`):

```bash
VIDEO_STAGE=quote VIDEO_ASSETS=tools/video_pipeline/assets \
    odoo shell -c odoo.conf -d tectora_video < tools/video_pipeline/seed_demo.py
```

The seed is idempotent and removes what an earlier take created, so every
take starts from the same screen.

## Making a video

```bash
RESET="odoo shell -c odoo.conf -d tectora_video < tools/video_pipeline/seed_demo.py"

# 1. Rehearse: headless, no recording; fails fast with error.png on a missing button
.venv-video/bin/python tools/video_pipeline/make_video.py \
    tools/video_pipeline/storyboards/standaard/04_offerte_maken.yaml \
    --db tectora_video --reset "$RESET" --capture none

# 2. Record
ODOO_PASSWORD=... .venv-video/bin/python tools/video_pipeline/make_video.py \
    tools/video_pipeline/storyboards/standaard/04_offerte_maken.yaml \
    --url http://localhost:8069 --db tectora_video --login admin --reset "$RESET" \
    --music muziek.mp3   # optional, ducks under the voice
```

Output in `build/videos/<storyboard>/`: `<name>.mp4` (1080p30, H.264/AAC),
`<name>.srt` (subtitles from the voice-over), `<name>.jpg` (thumbnail) and
`timeline.json`. A storyboard's `bumper` (the series uses
`docs/handleiding/dataforge_logo.png`) is shown before and after the video;
`--bumper` overrides it. `--voice-only` only synthesises the voice-over and
prints the length per shot against the script.

Record a series one video at a time: one Odoo serving several recordings at
once makes steps lag behind the voice-over.

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
      - fill: {field: partner_id, value: Peeters, pick: Peeters}
      - save:
      - highlight: {field: address, seconds: 2}
      - zoom: {selector: .o_statusbar_status, scale: 2}
      - wait: 1.5
```

Each shot shows its caption, runs its steps while the voice speaks, and holds
until the voice-over is done; so the voice decides the length, as the
scripts intend. A card's `kind: html` takes free HTML (see the diagram in
shot 2 of the example).

More steps (docstrings in `recorder.py`): `type`, `key`, `hover`, `drag`,
`edit_cell`, `scroll`, `scroll_to`, `unclip`, `card`/`hide_card` (a card in
the middle of a shot), `login` (switch user, under a card), `phone`/
`phone_close` (a portal page in a smartphone frame), `fetch_pdf`/`show_pdf`
(a printed report as a card), `open_here` and `back`. The eleven
storyboards in `storyboards/standaard/` are worked examples of all of them.

## Publishing

Upload the MP4 (unlisted on YouTube/Vimeo, or Google Drive) and add it as
*Video* content to the course in Odoo eLearning; the `.srt` goes along as
subtitles on YouTube/Vimeo.

## Limits

* The standard series (`storyboards/standaard/`, 11 videos) and
  `dakmeting_02` have storyboards; the other Dakmeting scripts need one each.
  Drawing on the canvas (Dakmeting 03/04) needs mouse-path steps that do
  not exist yet.
* Piper is free and offline but sounds synthetic; a paid voice (e.g.
  ElevenLabs) would slot in next to `tts.PiperVoice`.
* `--capture playwright` works on macOS/Windows without Xvfb, but the image
  is softer.
