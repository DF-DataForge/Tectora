"""Voice-over with Piper (offline, free, Flemish voices).

Each shot's text becomes one WAV, cached by text + voice, so a re-take only
synthesises the lines that changed.
"""

import hashlib
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import wave

VOICE_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
    "{lang}/{locale}/{speaker}/{quality}/{voice}{ext}"
)


def voice_files(voice, voice_dir):
    """Path to the .onnx model of a Piper voice, downloaded on first use.

    `voice` is a Piper voice name such as ``nl_BE-nathalie-medium``.
    """
    model = os.path.join(voice_dir, f"{voice}.onnx")
    if os.path.exists(model) and os.path.exists(model + ".json"):
        return model
    locale, speaker, quality = voice.split("-")
    os.makedirs(voice_dir, exist_ok=True)
    for ext in (".onnx", ".onnx.json"):
        url = VOICE_URL.format(
            lang=locale.split("_")[0], locale=locale, speaker=speaker,
            quality=quality, voice=voice, ext=ext,
        )
        print(f"  downloading {url}")
        urllib.request.urlretrieve(url, os.path.join(voice_dir, voice + ext))
    return model


def apply_pronunciation(text, pronunciation):
    """Rewrite words the voice gets wrong ("CRM" → "C R M") — audio only."""
    for word, spoken in (pronunciation or {}).items():
        text = re.sub(rf"(?<!\w){re.escape(word)}(?!\w)", spoken, text)
    return text


def wav_duration(path):
    with wave.open(path) as handle:
        return handle.getnframes() / handle.getframerate()


class PiperVoice:
    def __init__(self, voice, voice_dir, cache_dir, length_scale=1.0, pronunciation=None):
        # Next to the running interpreter first: a venv need not be activated.
        local = os.path.join(os.path.dirname(sys.executable), "piper")
        self.piper = local if os.path.exists(local) else shutil.which("piper")
        if not self.piper:
            raise SystemExit("piper not found: pip install -r requirements.txt")
        self.voice = voice
        self.model = voice_files(voice, voice_dir)
        self.cache_dir = cache_dir
        self.length_scale = length_scale
        self.pronunciation = pronunciation or {}
        os.makedirs(cache_dir, exist_ok=True)

    def say(self, text):
        """WAV path for `text` (synthesised once, then cached)."""
        spoken = apply_pronunciation(text, self.pronunciation)
        key = hashlib.sha1(
            f"{self.voice}|{self.length_scale}|{spoken}".encode()
        ).hexdigest()[:16]
        path = os.path.join(self.cache_dir, f"{key}.wav")
        if not os.path.exists(path):
            subprocess.run(
                [self.piper, "-m", self.model, "-f", path,
                 "--length-scale", str(self.length_scale),
                 "--sentence-silence", "0.25"],
                input=spoken.encode(), check=True, capture_output=True,
            )
        return path
