"""Explicit, bounded song-name search against Deezer's public metadata endpoint."""

import json
from dataclasses import dataclass

import httpx

from bxvzm import __version__

API_URL = "https://api.deezer.com/search"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
RESULT_LIMIT = 20


@dataclass(frozen=True)
class CatalogSong:
    title: str
    artist: str
    album: str
    track_url: str
    album_url: str
    explicit: bool | None
    provider: str = "Deezer"


class CatalogError(ValueError):
    """Catalog lookup failed; local playback and import remain available."""


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid catalog text")
    cleaned = " ".join("".join(c for c in value if c.isprintable() or c.isspace()).split())
    if not cleaned or len(cleaned) > 500:
        raise ValueError("Invalid catalog text")
    return cleaned


def _id(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError("Invalid catalog identifier")
    return value


def search_songs(query: str) -> list[CatalogSong]:
    """Return at most twenty catalog choices; never fetch audio or supplied URLs."""
    query = query.strip()
    if not query or len(query) > 200 or any(ord(c) < 32 for c in query):
        raise CatalogError("Enter a song and optionally an artist (1–200 characters)")
    try:
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            with client.stream(
                "GET",
                API_URL,
                params={"q": query, "limit": RESULT_LIMIT},
                headers={"User-Agent": f"bXVzaVM/{__version__} (personal catalog search)"},
            ) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    if len(body) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise CatalogError("Catalog response is too large; refine the search")
                    body.extend(chunk)
        payload = json.loads(body)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise ValueError("Invalid catalog response")
        if "error" in payload:
            raise CatalogError("Deezer could not complete this search; try again later")
        songs = []
        for record in payload["data"][:RESULT_LIMIT]:
            try:
                track_id = _id(record["id"])
                album_id = _id(record["album"]["id"])
                explicit = record.get("explicit_lyrics")
                songs.append(
                    CatalogSong(
                        title=_text(record["title"]),
                        artist=_text(record["artist"]["name"]),
                        album=_text(record["album"]["title"]),
                        track_url=f"https://www.deezer.com/track/{track_id}",
                        album_url=f"https://www.deezer.com/album/{album_id}",
                        explicit=explicit if type(explicit) is bool else None,
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        if payload["data"] and not songs:
            raise ValueError("No usable catalog records")
        return songs
    except CatalogError:
        raise
    except httpx.TimeoutException as error:
        raise CatalogError("Deezer search timed out; retry or refine the query") from error
    except httpx.HTTPError as error:
        raise CatalogError("Deezer search is unavailable; local music still works") from error
    except (ValueError, TypeError) as error:
        raise CatalogError("Deezer returned invalid metadata; try again later") from error
