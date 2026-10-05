import os
import re
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import write_wave
from textual.widgets import Button, DataTable, Input, Static

from bxvzm.library import LibraryLayout
from bxvzm.transfers.imports import stage_import
from bxvzm.ui import MusicApp
from bxvzm.ui.transfers import ImportPanel


class TransferInterfaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_stage_review_accept_in_small_terminal_and_no_import_row_playback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            layout = LibraryLayout.at(base / "data/library", base)
            source = write_wave(base / "downloads/song.wav")
            app = MusicApp(layout)
            main_thread = threading.get_ident()
            worker_threads = []

            def stage(*args, **kwargs):
                worker_threads.append(threading.get_ident())
                return stage_import(*args, **kwargs)

            async with app.run_test(size=(80, 24)) as pilot:
                await app.workers.wait_for_complete()
                await pilot.press("5")
                app.query_one("#import-path", Input).value = str(source)
                with patch("bxvzm.ui.transfers.stage_import", side_effect=stage):
                    await pilot.click("#stage-import")
                    await app.workers.wait_for_complete()
                await pilot.pause()
                self.assertTrue(worker_threads)
                self.assertNotIn(main_thread, worker_threads)
                jobs = app.store.list_imports()
                self.assertEqual(jobs[0]["state"], "review")
                self.assertEqual(app.store.list_tracks(), [])
                self.assertIn(
                    "Completeness: unknown", str(app.query_one("#import-detail", Static).content)
                )
                table = app.query_one("#import-jobs", DataTable)
                table.focus()
                with (
                    patch.object(app, "_send_player") as player,
                    patch.object(app, "_library_task") as library,
                ):
                    await pilot.press("enter", "f")
                player.assert_not_called()
                library.assert_not_called()
                if screenshot_directory := os.environ.get("BXVZM_SCREENSHOT_DIR"):
                    app.query_one("#import-path", Input).value = "data/downloads/song.wav"
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
                    screenshot = "\n".join(line.rstrip() for line in screenshot.splitlines()) + "\n"
                    path = Path(screenshot_directory) / "imports.svg"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(screenshot, encoding="utf-8")
                button = app.query_one("#accept-import", Button)
                button.scroll_visible(animate=False)
                await pilot.pause()
                await pilot.click("#accept-import")
                await app.workers.wait_for_complete()
                await pilot.pause()
                self.assertEqual(app.store.list_imports()[0]["state"], "committed")
                self.assertEqual(app.query_one("#tracks", DataTable).row_count, 1)
                self.assertTrue(source.exists())
                self.assertFalse(app.query_one(ImportPanel).busy)

    async def test_invalid_link_and_import_error_leave_interface_usable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            app = MusicApp(LibraryLayout.at(base / "data/library", base))
            async with app.run_test(size=(80, 24)) as pilot:
                await app.workers.wait_for_complete()
                await pilot.press("2")
                app.query_one("#download-url", Input).value = "https://evil.test/song"
                with patch("bxvzm.ui.transfers.open_download_page") as browser:
                    await pilot.click("#open-download")
                    await app.workers.wait_for_complete()
                browser.assert_not_called()
                self.assertIn(
                    "direct Deezer", str(app.query_one("#download-status", Static).content)
                )
                await pilot.press("5")
                app.query_one("#import-path", Input).value = str(base / "missing.zip")
                await pilot.click("#stage-import")
                await app.workers.wait_for_complete()
                await pilot.pause()
                self.assertFalse(app.query_one("#stage-import", Button).disabled)
                self.assertIn("existing file", str(app.query_one("#import-detail", Static).content))
