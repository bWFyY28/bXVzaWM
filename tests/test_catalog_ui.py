import os
import re
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from textual.widgets import Button, DataTable, Input, Static, TabbedContent

from bxvzm.catalog.deezer import CatalogError, CatalogSong
from bxvzm.library import LibraryLayout
from bxvzm.ui import MusicApp
from bxvzm.ui.catalog import CatalogPanel

SONG = CatalogSong(
    "Circles",
    "Post Malone",
    "Hollywood's Bleeding",
    "https://www.deezer.com/track/1",
    "https://www.deezer.com/album/2",
    None,
)


class CatalogInterfaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_name_search_selection_and_prefill_without_pasting_or_playback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = MusicApp(LibraryLayout.at(root / "data/library", root))
            async with app.run_test(size=(80, 24)) as pilot:
                await app.workers.wait_for_complete()
                await pilot.press("2")
                app.query_one("#catalog-query", Input).value = "Circles Post Malone"
                with patch("bxvzm.ui.catalog.search_songs", return_value=[SONG]) as search:
                    await pilot.click("#search-catalog")
                    await app.workers.wait_for_complete()
                search.assert_called_once_with("Circles Post Malone")
                self.assertEqual(app.query_one("#catalog-results", DataTable).row_count, 1)
                with patch.object(app, "_send_player") as player:
                    await pilot.press("enter")
                player.assert_not_called()
                self.assertEqual(app.query_one("#download-url", Input).value, SONG.album_url)
                self.assertEqual(app.focused.id, "open-download")
                with patch("bxvzm.ui.transfers.open_download_page") as browser:
                    await pilot.press("enter")
                    await app.workers.wait_for_complete()
                self.assertEqual(browser.call_args.args[0].url, SONG.album_url)
                self.assertIn(
                    "URL filled in", str(app.query_one("#download-status", Static).content)
                )
                app.query_one("#use-track", Button).scroll_visible(animate=False)
                await pilot.pause()
                await pilot.click("#use-track")
                self.assertEqual(app.query_one("#download-url", Input).value, SONG.track_url)
                panel = app.query_one(CatalogPanel)
                panel.scroll_home(animate=False)
                await pilot.pause()
                if screenshot_directory := os.environ.get("BXVZM_SCREENSHOT_DIR"):
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

    async def test_offline_worker_keeps_navigation_responsive_and_clears_stale_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = MusicApp(LibraryLayout.at(root / "data/library", root))
            unblock = threading.Event()
            worker_threads = []

            def slow_search(query):
                worker_threads.append(threading.get_ident())
                unblock.wait(3)
                raise CatalogError("Deezer search is unavailable; local music still works")

            async with app.run_test(size=(80, 24)) as pilot:
                await app.workers.wait_for_complete()
                await pilot.press("2")
                app.query_one("#catalog-query", Input).value = "Circles"
                app.query_one("#download-url", Input).value = SONG.album_url
                with patch("bxvzm.ui.catalog.search_songs", side_effect=slow_search):
                    try:
                        await pilot.click("#search-catalog")
                        await pilot.press("1")
                        self.assertEqual(app.query_one(TabbedContent).active, "library")
                    finally:
                        unblock.set()
                    await app.workers.wait_for_complete()
                self.assertTrue(worker_threads)
                self.assertNotIn(threading.get_ident(), worker_threads)
                self.assertFalse(app.query_one(CatalogPanel).busy)
                self.assertFalse(app.query_one("#search-catalog", Button).disabled)
                self.assertTrue(app.query_one("#use-album", Button).disabled)
                self.assertEqual(app.query_one("#download-url", Input).value, "")
                self.assertIn("unavailable", str(app.query_one("#catalog-status", Static).content))
