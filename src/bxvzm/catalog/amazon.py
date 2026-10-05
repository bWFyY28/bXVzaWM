"""Amazon's public browser search; no private catalog requests or provider substitution."""

import webbrowser
from urllib.parse import quote


def search_url(query: str) -> str:
    query = query.strip()
    if not query or len(query) > 200 or any(ord(character) < 32 for character in query):
        raise ValueError("Enter a song name and optionally an artist (1-200 characters)")
    return "https://music.amazon.com/search/" + quote(query, safe="")


def open_search(query: str) -> None:
    url = search_url(query)
    if not webbrowser.open(url, new=2):
        raise RuntimeError(f"Open {url} in your browser to search Amazon Music")
