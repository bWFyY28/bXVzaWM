"""Synthetic audio only; tests never read the user's music."""

import wave
from pathlib import Path

from mutagen.id3 import TALB, TIT2, TPE1, TPOS, TRCK
from mutagen.wave import WAVE


def write_wave(path: Path, title: str = "Circles", artist: str = "Post Malone") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\x00\x00" * 8000)
    metadata = WAVE(path)
    metadata.add_tags()
    metadata.tags.add(TIT2(encoding=3, text=title))
    metadata.tags.add(TPE1(encoding=3, text=artist))
    metadata.tags.add(TALB(encoding=3, text="Test album"))
    metadata.tags.add(TPOS(encoding=3, text="2/2"))
    metadata.tags.add(TRCK(encoding=3, text="3/10"))
    metadata.save()
    return path
