#!/usr/bin/env python3
"""Turn a video script + storyboard into a finished explainer video.

    python tools/video_pipeline/make_video.py \\
        tools/video_pipeline/storyboards/dakmeting_02_dakproject_starten.yaml \\
        --url http://localhost:8069 --login admin

See tools/video_pipeline/README.md.
"""

import argparse
import json
import os
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

from script_md import parse_script  # noqa: E402
from tts import PiperVoice, wav_duration  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("storyboard", help="storyboard YAML file")
    parser.add_argument("--url", default=os.environ.get("ODOO_URL", "http://localhost:8069"))
    parser.add_argument("--login", default=os.environ.get("ODOO_LOGIN", "admin"))
    parser.add_argument("--password", default=os.environ.get("ODOO_PASSWORD", "admin"),
                        help="defaults to $ODOO_PASSWORD")
    parser.add_argument("--out", default=os.path.join(REPO, "build", "videos"))
    parser.add_argument("--voice", help="Piper voice, overrides the storyboard")
    parser.add_argument("--voice-dir", default=os.path.expanduser("~/.cache/tectora-video/voices"))
    parser.add_argument("--music", help="background music file (ducked under the voice)")
    parser.add_argument("--capture", choices=("x11", "playwright", "none"),
                        default="x11" if sys.platform.startswith("linux") else "playwright",
                        help="x11: sharp Xvfb capture (Linux); playwright: anywhere; none: rehearsal")
    parser.add_argument("--display", help="record an existing X display instead of a private Xvfb")
    parser.add_argument("--chromium", default=os.environ.get("CHROMIUM_PATH"),
                        help="Chromium executable (default: Playwright's own)")
    parser.add_argument("--reset", help="shell command run before recording, e.g. the demo seed")
    parser.add_argument("--voice-only", action="store_true",
                        help="only synthesise the voice-over and print the timing")
    args = parser.parse_args()

    with open(args.storyboard, encoding="utf-8") as handle:
        board = yaml.safe_load(handle)
    script = parse_script(os.path.join(REPO, board["script"]))
    name = board.get("name") or os.path.splitext(os.path.basename(args.storyboard))[0]
    out_dir = os.path.join(args.out, name)
    os.makedirs(out_dir, exist_ok=True)
    print(f"{script.title} — {len(script.shots)} shots → {out_dir}")

    # 1. Voice-over
    voice = PiperVoice(
        args.voice or board.get("voice", "nl_BE-nathalie-medium"),
        args.voice_dir,
        os.path.join(args.out, ".tts-cache"),
        length_scale=float(board.get("tempo", 1.0)),
        pronunciation=board.get("pronunciation"),
    )
    clips = {}
    total = 0.0
    for shot in script.shots:
        if shot.voice_over:
            path = voice.say(shot.voice_over)
            clips[shot.number] = {"path": path, "duration": wav_duration(path)}
            total += clips[shot.number]["duration"]
            print(f"  voice {shot.number}: {clips[shot.number]['duration']:.1f}s "
                  f"(script {shot.scripted_duration:.0f}s)")
    print(f"  voice-over total {total:.1f}s, script {script.shots[-1].scripted_end}s")
    if args.voice_only:
        return

    # 2. Demo data back to its starting point
    if args.reset:
        print(f"reset: {args.reset}")
        subprocess.run(args.reset, shell=True, check=True)

    # 3. Record
    from recorder import record
    from assemble import assemble

    meta = record(script, board, clips, out_dir, args.url, args.login, args.password,
                  capture=args.capture, display=args.display, chromium=args.chromium)
    if args.capture == "none":
        print("rehearsal OK: every step found its target")
        return

    # 4. Assemble
    result = assemble(meta, out_dir, name, music=args.music or board.get("music"),
                      thumbnail_shot=board.get("thumbnail_shot"))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
