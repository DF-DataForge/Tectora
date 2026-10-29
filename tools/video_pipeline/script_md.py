"""Read a video script (docs/video_scripts/**.md) into shots.

The Markdown script stays the single source for what is *said* (Voice-over)
and *shown as text* (Tekst in beeld); the storyboard only adds what the
browser has to *do* per shot.
"""

import re
from dataclasses import dataclass, field

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_TIME = re.compile(r"(\d+):(\d{2})\s*[–-]\s*(\d+):(\d{2})")
_EMPTY = {"", "—", "-", "–"}


def plain(text):
    """Markdown cell → plain text (drops ** and surrounding whitespace)."""
    text = _BOLD.sub(r"\1", text or "").strip()
    return "" if text in _EMPTY else text


@dataclass
class Shot:
    number: int
    scripted_start: float
    scripted_end: float
    picture: str
    voice_over: str
    caption: str

    @property
    def scripted_duration(self):
        return max(self.scripted_end - self.scripted_start, 0.0)


@dataclass
class Script:
    path: str
    title: str
    shots: list = field(default_factory=list)

    def shot(self, number):
        for shot in self.shots:
            if shot.number == number:
                return shot
        raise KeyError(f"{self.path}: no shot {number}")


def _seconds(minutes, seconds):
    return int(minutes) * 60 + int(seconds)


def parse_script(path):
    with open(path, encoding="utf-8") as handle:
        lines = handle.read().splitlines()

    title = ""
    for line in lines:
        if line.startswith("# "):
            # "# 02 — Een dakproject starten" → "Een dakproject starten"
            title = re.split(r"\s+[—–-]\s+", line[2:].strip(), maxsplit=1)[-1]
            break

    header = None
    shots = []
    for line in lines:
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if header is None:
            if cells and cells[0] == "#":
                header = [cell.lower() for cell in cells]
            continue
        if set("".join(cells)) <= set("-: "):
            continue  # separator row
        row = dict(zip(header, cells))
        time = _TIME.search(row.get("tijd", ""))
        if not time or not row.get("#", "").isdigit():
            continue
        shots.append(
            Shot(
                number=int(row["#"]),
                scripted_start=_seconds(*time.group(1, 2)),
                scripted_end=_seconds(*time.group(3, 4)),
                picture=plain(row.get("beeld")),
                voice_over=plain(row.get("voice-over")),
                caption=plain(row.get("tekst in beeld")),
            )
        )
    if not shots:
        raise ValueError(f"{path}: no shot table found")
    return Script(path=path, title=title, shots=shots)
