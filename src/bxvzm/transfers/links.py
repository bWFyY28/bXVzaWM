"""Validated provider links for the manual DoubleDouble browser workflow."""

import re
import webbrowser
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

DOUBLEDOUBLE_URL = "https://us.doubledouble.top/"
AMAZON_HOSTS = frozenset(
    f"music.amazon.{region}"
    for region in (
        "com",
        "co.uk",
        "de",
        "fr",
        "it",
        "es",
        "co.jp",
        "ca",
        "com.au",
        "com.br",
        "in",
        "com.mx",
    )
)


@dataclass(frozen=True)
class ProviderLink:
    provider: str
    kind: str
    url: str


def validate_provider_url(value: str) -> ProviderLink:
    value = value.strip()
    if len(value) > 2048 or any(ord(character) < 33 for character in value) or "\\" in value:
        raise ValueError("Paste a complete HTTPS album or track link")
    parts = urlsplit(value)
    if parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443):
        raise ValueError("Provider links must use HTTPS without credentials or custom ports")
    host = parts.hostname or ""
    path = parts.path.rstrip("/")
    match = None
    provider = ""
    if host in ("deezer.com", "www.deezer.com"):
        provider = "Deezer"
        match = re.fullmatch(r"/(?:[a-z]{2}/)?(album|track)/([0-9]+)", path)
    elif host in ("tidal.com", "www.tidal.com", "listen.tidal.com"):
        provider = "TIDAL"
        match = re.fullmatch(r"/(?:browse/)?(album|track)/([0-9]+)", path)
    elif host in AMAZON_HOSTS:
        provider = "Amazon Music"
        match = re.fullmatch(r"/(albums|tracks)/([A-Za-z0-9]+)", path)
    if match is None:
        raise ValueError("Use a direct Deezer, TIDAL, or Amazon Music album/track link")
    # Amazon's album ?trackAsin= identifies a track; retain only that selector.
    query = ""
    if provider == "Amazon Music" and parts.query:
        from urllib.parse import parse_qs, urlencode

        selectors = parse_qs(parts.query).get("trackAsin", [])
        if selectors:
            if len(selectors) != 1 or not re.fullmatch(r"[A-Za-z0-9]+", selectors[0]):
                raise ValueError("Invalid Amazon track selector")
            query = urlencode({"trackAsin": selectors[0]})
    return ProviderLink(
        provider, match[1].rstrip("s"), urlunsplit(("https", host, path, query, ""))
    )


def open_download_page(link: ProviderLink) -> None:
    """Open only the fixed handoff site; submit the provider URL manually."""
    validate_provider_url(link.url)
    if not webbrowser.open(DOUBLEDOUBLE_URL, new=2):
        raise RuntimeError(f"Open {DOUBLEDOUBLE_URL} in your browser and paste {link.url}")
