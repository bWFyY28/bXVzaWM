import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httpx

from bxvzm.catalog.deezer import API_URL, CatalogError, CatalogSong, search_songs
from bxvzm.cli import main
from bxvzm.transfers.links import ProviderLink, download_page_url


def record(**changes):
    result = {
        "id": 742744952,
        "title": "Circles",
        "artist": {"name": "Post Malone"},
        "album": {"id": 109313692, "title": "Circles"},
        "explicit_lyrics": False,
        "link": "https://evil.test/not-a-provider-link",
    }
    result.update(changes)
    return result


class CatalogTests(unittest.TestCase):
    def response(self, payload, *, status=200, query="Circles Post Malone"):
        requests = []

        def handle(request):
            requests.append(request)
            return httpx.Response(status, json=payload)

        client = httpx.Client(transport=httpx.MockTransport(handle))
        with patch("bxvzm.catalog.deezer.httpx.Client", return_value=client):
            songs = search_songs(query)
        return songs, requests

    def test_search_metadata_and_built_provider_links_without_local_assumptions(self):
        songs, requests = self.response({"data": [record()]})
        self.assertEqual(str(requests[0].url).split("?")[0], API_URL)
        self.assertEqual(requests[0].url.params["q"], "Circles Post Malone")
        self.assertEqual(songs[0].title, "Circles")
        self.assertEqual(songs[0].artist, "Post Malone")
        self.assertEqual(songs[0].album_url, "https://www.deezer.com/album/109313692")
        self.assertEqual(songs[0].track_url, "https://www.deezer.com/track/742744952")
        self.assertFalse(songs[0].explicit)
        self.assertEqual(songs[0].provider, "Deezer")

    def test_missing_explicit_and_bad_records_do_not_create_false_metadata(self):
        songs, _ = self.response(
            {"data": [None, record(id=-1), record(explicit_lyrics=0), record(title="\0")]}
        )
        self.assertEqual(len(songs), 1)
        self.assertIsNone(songs[0].explicit)
        with self.assertRaises(CatalogError):
            self.response({"data": [record(id="123")]})

    def test_empty_errors_redirects_and_invalid_json_are_retryable(self):
        songs, _ = self.response({"data": []})
        self.assertEqual(songs, [])
        for payload, status in (
            ({"error": {"code": 4}}, 200),
            ({"data": []}, 429),
            ({"data": []}, 302),
            ([], 200),
        ):
            with self.subTest(status=status, payload=payload), self.assertRaises(CatalogError):
                self.response(payload, status=status)
        client = httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"bad json"))
        )
        with (
            patch("bxvzm.catalog.deezer.httpx.Client", return_value=client),
            self.assertRaises(CatalogError),
        ):
            search_songs("Circles")

    def test_timeout_size_limit_and_invalid_query(self):
        def timeout(request):
            raise httpx.ReadTimeout("slow", request=request)

        client = httpx.Client(transport=httpx.MockTransport(timeout))
        with (
            patch("bxvzm.catalog.deezer.httpx.Client", return_value=client),
            self.assertRaisesRegex(CatalogError, "timed out"),
        ):
            search_songs("Circles")
        with (
            patch("bxvzm.catalog.deezer.MAX_RESPONSE_BYTES", 10),
            self.assertRaisesRegex(CatalogError, "too large"),
        ):
            self.response({"data": [record()]})
        for query in ("", " ", "x" * 201, "song\nartist"):
            with (
                self.subTest(query=query),
                patch("bxvzm.catalog.deezer.httpx.Client") as client,
                self.assertRaises(CatalogError),
            ):
                search_songs(query)
            client.assert_not_called()

    def test_query_url_cannot_change_request_host_and_results_are_bounded(self):
        songs, requests = self.response(
            {"data": [record(id=i) for i in range(1, 25)]}, query="https://evil.test/?limit=999"
        )
        self.assertEqual(requests[0].url.host, "api.deezer.com")
        self.assertEqual(len(songs), 20)

    def test_double_double_prefill_encodes_nested_amazon_selector(self):
        link = ProviderLink(
            "Amazon Music", "album", "https://music.amazon.com/albums/B1?trackAsin=B2&ref=test#x"
        )
        url = download_page_url(link)
        parts = urlsplit(url)
        self.assertEqual(
            (parts.scheme, parts.netloc, parts.path), ("https", "us.doubledouble.top", "/")
        )
        self.assertEqual(
            parse_qs(parts.query), {"url": ["https://music.amazon.com/albums/B1?trackAsin=B2"]}
        )
        self.assertEqual(parts.fragment, "")

    def test_cli_name_search_choice_and_prefill_never_start_player(self):
        song = CatalogSong(
            "Circles",
            "Post Malone",
            "Circles",
            "https://www.deezer.com/track/1",
            "https://www.deezer.com/album/2",
            None,
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("bxvzm.config.application_root", return_value=Path(directory)),
            patch("bxvzm.catalog.deezer.search_songs", return_value=[song]),
            patch("bxvzm.service.start_service") as player,
            patch("bxvzm.transfers.links.webbrowser.open", return_value=True) as browser,
        ):
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(
                    main(["--provider", "deezer", "--search", "circle post malone"]), 0
                )
                self.assertIn("Post Malone", output.getvalue())
                self.assertIn("Explicit (track): unknown", output.getvalue())
            browser.assert_not_called()
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "--provider",
                            "deezer",
                            "--search",
                            "circle post malone",
                            "--result",
                            "1",
                            "--open-browser",
                        ]
                    ),
                    0,
                )
            self.assertEqual(
                parse_qs(urlsplit(browser.call_args.args[0]).query)["url"], [song.album_url]
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main(
                        [
                            "--provider",
                            "deezer",
                            "--search",
                            "circle",
                            "--result",
                            "1",
                            "--track-link",
                            "--open-browser",
                        ]
                    ),
                    0,
                )
            self.assertEqual(
                parse_qs(urlsplit(browser.call_args.args[0]).query)["url"], [song.track_url]
            )
            with redirect_stderr(io.StringIO()):
                self.assertEqual(
                    main(["--provider", "deezer", "--search", "circle", "--result", "2"]), 1
                )
        player.assert_not_called()
