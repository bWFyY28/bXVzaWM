"""Local file metadata, kept separate from future catalog release evidence."""

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_SUFFIXES = frozenset({".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wav"})


@dataclass(frozen=True)
class Track:
    relative_path: str
    title: str
    artist: str
    album: str
    album_artist: str
    disc_number: int
    track_number: int
    duration: float
    format: str
    sample_rate: int
    bits_per_sample: int
    bitrate: int
    sha256: str
    size: int
    mtime_ns: int
    favorite: bool = False
    available: bool = True


def read_track(path: Path, relative_path: str, *, fallback_title: str | None = None) -> Track:
    """Read and hash source bytes without modifying tags or audio."""
    import mutagen

    before = path.stat()
    audio = mutagen.File(path, easy=True)
    if audio is None or audio.info is None:
        raise ValueError("Unrecognized audio file")
    tags = audio.tags or {}

    def text(key: str, fallback: str, id3_key: str = "") -> str:
        value = tags.get(key) or tags.get(id3_key)
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        # WAV uses native ID3 frames even with easy=True.
        value = str(value or "")
        value = " ".join("".join(c for c in value if c.isprintable() or c.isspace()).split())
        return value or fallback

    def number(key: str, id3_key: str) -> int:
        try:
            return max(0, int(text(key, "0", id3_key).split("/")[0]))
        except ValueError:
            return 0

    duration = float(audio.info.length)
    if not math.isfinite(duration) or duration < 0:
        raise ValueError("Invalid audio duration")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("File changed during scanning; rescan after copying finishes")
    artist = text("artist", "Unknown artist", "TPE1")
    return Track(
        relative_path=relative_path,
        title=text("title", fallback_title or path.stem, "TIT2"),
        artist=artist,
        album=text("album", "Unknown album", "TALB"),
        album_artist=text("albumartist", artist, "TPE2"),
        disc_number=number("discnumber", "TPOS"),
        track_number=number("tracknumber", "TRCK"),
        duration=duration,
        format=path.suffix[1:].upper(),
        sample_rate=int(getattr(audio.info, "sample_rate", 0) or 0),
        bits_per_sample=int(getattr(audio.info, "bits_per_sample", 0) or 0),
        bitrate=int(getattr(audio.info, "bitrate", 0) or 0),
        sha256=digest,
        size=after.st_size,
        mtime_ns=after.st_mtime_ns,
    )
