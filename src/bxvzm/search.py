"""Small deterministic fuzzy search over local metadata."""

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from bxvzm.metadata import Track


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(re.findall(r"\w+", "".join(c for c in value if not unicodedata.combining(c))))


@dataclass(frozen=True)
class Match:
    track: Track
    score: float


def find_songs(tracks: list[Track], query: str, limit: int = 5) -> list[Match]:
    needle = normalized(query)
    if not needle:
        return []
    matches = []
    for track in tracks:
        if not track.available:
            continue
        title = normalized(track.title)
        artist = normalized(track.artist)
        candidates = (title, f"{title} {artist}", f"{artist} {title}")
        score = max(SequenceMatcher(None, needle, value).ratio() for value in candidates)
        if needle == title:
            score = 1.0
        elif needle in title:
            score = max(score, 0.88)
        if score >= 0.55:
            matches.append(Match(track, score))
    return sorted(matches, key=lambda match: (-match.score, match.track.relative_path))[:limit]
