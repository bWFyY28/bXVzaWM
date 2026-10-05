import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, unquote, urlsplit

from bxvzm.catalog.amazon import open_search, search_url
from bxvzm.cli import main
from bxvzm.transfers.clipboard import copied_amazon_link


class AmazonTests(unittest.TestCase):
    def test_browser_search_fixed_origin_and_encoded_query(self):
        parts = urlsplit(search_url("Circles Post Malone/?url=https://evil.test"))
        self.assertEqual(parts.netloc, "music.amazon.com")
        self.assertEqual(parts.query, "")
        self.assertEqual(
            unquote(parts.path[len("/search/") :]), "Circles Post Malone/?url=https://evil.test"
        )
        with (
            patch("bxvzm.catalog.amazon.webbrowser.open", return_value=False),
            self.assertRaisesRegex(RuntimeError, "music.amazon.com"),
        ):
            open_search("Circles")
        for query in ("", " ", "x" * 201, "song\nartist"):
            with self.assertRaises(ValueError):
                search_url(query)

    def test_clipboard_only_reads_on_request_rejects_other_providers_and_closes(self):
        clipboard = Mock()
        clipboard.CF_UNICODETEXT = 13
        clipboard.IsClipboardFormatAvailable.return_value = True
        modules = {"pywintypes": SimpleNamespace(error=OSError), "win32clipboard": clipboard}
        with patch("bxvzm.transfers.clipboard.os.name", "nt"), patch.dict(sys.modules, modules):
            clipboard.GetClipboardData.return_value = (
                "https://music.amazon.com/albums/B07X3R97JH?ref=x"
            )
            self.assertEqual(copied_amazon_link().url, "https://music.amazon.com/albums/B07X3R97JH")
            clipboard.CloseClipboard.assert_called_once()
            for value in (
                "https://www.deezer.com/album/1",
                "https://music.amazon.com.evil.test/albums/ABC",
                "unrelated clipboard text",
            ):
                clipboard.GetClipboardData.return_value = value
                with self.assertRaises(ValueError):
                    copied_amazon_link()
            self.assertEqual(clipboard.CloseClipboard.call_count, 4)
        with (
            patch("bxvzm.transfers.clipboard.os.name", "posix"),
            self.assertRaisesRegex(ValueError, "native Windows"),
        ):
            copied_amazon_link()

    def test_cli_defaults_to_amazon_and_prefills_only_copied_amazon_link(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("bxvzm.config.application_root", return_value=Path(directory)),
            patch("bxvzm.catalog.amazon.webbrowser.open", return_value=True) as browser,
        ):
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["--search", "Circles Post Malone", "--open-browser"]), 0)
            self.assertIn("Amazon Music search", output.getvalue())
            self.assertEqual(urlsplit(browser.call_args.args[0]).netloc, "music.amazon.com")
            from bxvzm.transfers.links import validate_provider_url

            link = validate_provider_url("https://music.amazon.com/albums/B07X3R97JH")
            with (
                patch("bxvzm.transfers.clipboard.copied_amazon_link", return_value=link),
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(main(["--download-copied", "--open-browser"]), 0)
            self.assertEqual(parse_qs(urlsplit(browser.call_args.args[0]).query)["url"], [link.url])
