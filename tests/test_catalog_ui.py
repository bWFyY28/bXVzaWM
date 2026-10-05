import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from textual.widgets import Button, Input, Static

from bxvzm.library import LibraryLayout
from bxvzm.transfers.links import validate_provider_url
from bxvzm.ui import MusicApp

AMAZON_URL = "https://music.amazon.com/albums/B07X3R97JH"


class CatalogInterfaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_amazon_search_copied_link_and_prefill_without_playback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = MusicApp(LibraryLayout.at(root / "data/library", root))
            async with app.run_test(size=(80, 24)) as pilot:
                await app.workers.wait_for_complete()
                await pilot.press("2")
                app.query_one("#catalog-query", Input).value = "Circles Post Malone"
                with patch("bxvzm.ui.catalog.open_search") as search:
                    await pilot.click("#search-catalog")
                    await app.workers.wait_for_complete()
                search.assert_called_once_with("Circles Post Malone")
                button = app.query_one("#use-copied-amazon", Button)
                button.disabled = False  # Exercise native clipboard UI on Linux too.
                with (
                    patch(
                        "bxvzm.ui.catalog.copied_amazon_link",
                        return_value=validate_provider_url(AMAZON_URL),
                    ),
                    patch.object(app, "_send_player") as player,
                ):
                    await pilot.click("#use-copied-amazon")
                    await app.workers.wait_for_complete()
                player.assert_not_called()
                self.assertEqual(app.query_one("#download-url", Input).value, AMAZON_URL)
                self.assertEqual(app.focused.id, "open-download")
                with patch("bxvzm.ui.transfers.open_download_page") as browser:
                    await pilot.press("enter")
                    await app.workers.wait_for_complete()
                self.assertEqual(browser.call_args.args[0].url, AMAZON_URL)
                self.assertIn(
                    "URL filled in", str(app.query_one("#download-status", Static).content)
                )
                if screenshot_directory := os.environ.get("BXVZM_SCREENSHOT_DIR"):
                    app.query_one("#catalog-query", Input).scroll_visible(animate=False)
                    await pilot.pause()
                    screenshot = app.export_screenshot()
                    screenshot = re.sub(r"@font-face\s*\{.*?\}", "", screenshot, flags=re.S)
                    screenshot = screenshot.replace(
                        "Fira Code, monospace", "'JetBrainsMono Nerd Font', monospace"
                    )
                    screenshot = screenshot.replace(
                        "font-family: arial;", "font-family: 'JetBrainsMono Nerd Font', monospace;"
                    )
                    screenshot = re.sub(r"<circle\b[^>]*/>", "", screenshot)
                    path = Path(screenshot_directory) / "search.svg"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(
                        "\n".join(line.rstrip() for line in screenshot.splitlines()) + "\n",
                        encoding="utf-8",
                    )
            self.assertFalse(app.layout.root.exists())

    async def test_clipboard_error_keeps_selection_and_navigation_usable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = MusicApp(LibraryLayout.at(root / "data/library", root))
            async with app.run_test(size=(80, 24)) as pilot:
                await app.workers.wait_for_complete()
                await pilot.press("2")
                app.query_one("#download-url", Input).value = AMAZON_URL
                app.query_one("#use-copied-amazon", Button).disabled = False
                with patch(
                    "bxvzm.ui.catalog.copied_amazon_link",
                    side_effect=ValueError("Copy an Amazon Music link first"),
                ):
                    await pilot.click("#use-copied-amazon")
                    await app.workers.wait_for_complete()
                self.assertIn(
                    "Amazon Music link first", str(app.query_one("#catalog-status", Static).content)
                )
                self.assertEqual(app.query_one("#download-url", Input).value, AMAZON_URL)
                await pilot.press("1")
