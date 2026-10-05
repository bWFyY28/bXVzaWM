import importlib.util
import os
import re
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import write_wave

from bxvzm.library import LibraryLayout

HAS_TEXTUAL = importlib.util.find_spec("textual") is not None


@unittest.skipUnless(HAS_TEXTUAL, "Install locked dependencies to run Textual checks")
class InterfaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_navigation_help_and_layout_at_80_by_24(self) -> None:
        from textual.widgets import Static, TabbedContent

        from bxvzm.ui import HelpScreen, MusicApp

        with tempfile.TemporaryDirectory() as directory:
            layout = LibraryLayout.at(
                Path(directory) / "data" / "library", app_root=Path(directory)
            )
            app = MusicApp(layout)
            async with app.run_test(size=(80, 24)) as pilot:
                self.assertEqual(app.query_one(TabbedContent).active, "library")
                for key, view in (
                    ("2", "search"),
                    ("3", "favorites"),
                    ("4", "playlists"),
                    ("5", "imports"),
                    ("1", "library"),
                ):
                    await pilot.press(key)
                    self.assertEqual(app.query_one(TabbedContent).active, view)
                player = app.query_one("#player", Static)
                self.assertGreater(player.region.height, 0)
                self.assertLessEqual(player.region.bottom, 24)
                self.assertGreater(app.query_one("#library-root", Static).region.height, 0)
                await pilot.press("question_mark")
                self.assertIsInstance(app.screen, HelpScreen)
                await pilot.press("escape")
                self.assertNotIsInstance(app.screen, HelpScreen)
                if screenshot_directory := os.environ.get("BXVZM_SCREENSHOT_DIR"):
                    app.save_screenshot("foundation.svg", path=screenshot_directory)
                    screenshot_path = Path(screenshot_directory) / "foundation.svg"
                    screenshot = screenshot_path.read_text(encoding="utf-8")
                    screenshot = re.sub(r"@font-face\s*\{.*?\}", "", screenshot, flags=re.S)
                    screenshot = screenshot.replace(
                        "Fira Code, monospace", "'JetBrainsMono Nerd Font', monospace"
                    )
                    screenshot = screenshot.replace(
                        "font-family: arial;", "font-family: 'JetBrainsMono Nerd Font', monospace;"
                    )
                    screenshot = re.sub(r"<circle\b[^>]*/>", "", screenshot)
                    screenshot = "\n".join(line.rstrip() for line in screenshot.splitlines()) + "\n"
                    screenshot_path.write_text(screenshot, encoding="utf-8")
                await pilot.press("q")
            # UI construction and navigation must not create library data.
            self.assertFalse(layout.root.exists())

    async def test_index_filter_favorites_and_text_input_shortcuts(self) -> None:
        from textual.widgets import DataTable, Input

        from bxvzm.database import LibraryStore
        from bxvzm.indexing import scan_library
        from bxvzm.ui import MusicApp

        with tempfile.TemporaryDirectory() as directory:
            layout = LibraryLayout.at(Path(directory) / "data/library", app_root=Path(directory))
            store = LibraryStore(layout)
            store.initialize()
            write_wave(layout.music / "circles.wav")
            write_wave(layout.music / "other.wav", "Another song", "Test artist")
            scan_library(store)
            app = MusicApp(layout)
            async with app.run_test(size=(80, 24)) as pilot:
                await app.workers.wait_for_complete()
                await pilot.pause()
                self.assertEqual(app.query_one("#tracks", DataTable).row_count, 2)
                self.assertEqual(app.animation_level, "none")
                self.assertEqual(len(app.query("HeaderIcon")), 0)
                await pilot.press("f")
                await app.workers.wait_for_complete()
                await pilot.pause()
                self.assertEqual(app.query_one("#favorite-tracks", DataTable).row_count, 1)
                await pilot.press("slash")
                with patch.object(app, "action_scan") as scan:
                    await pilot.press("c", "i", "r", "l", "e")
                    scan.assert_not_called()
                self.assertIsInstance(app.focused, Input)
                self.assertEqual(app.query_one("#tracks", DataTable).row_count, 1)
                await pilot.press("enter")
                self.assertIsInstance(app.focused, DataTable)
                await pilot.press("r")
                await app.workers.wait_for_complete()
                await pilot.pause()
                self.assertEqual(app.query_one("#tracks", DataTable).row_count, 1)
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
                    screenshot = "\n".join(line.rstrip() for line in screenshot.splitlines()) + "\n"
                    Path(screenshot_directory).mkdir(parents=True, exist_ok=True)
                    (Path(screenshot_directory) / "library.svg").write_text(
                        screenshot, encoding="utf-8"
                    )

    async def test_navigation_remains_responsive_during_scan(self) -> None:
        from textual.widgets import TabbedContent

        from bxvzm.indexing import ScanReport
        from bxvzm.ui import MusicApp

        with tempfile.TemporaryDirectory() as directory:
            layout = LibraryLayout.at(Path(directory) / "data/library", app_root=Path(directory))
            app = MusicApp(layout)
            unblock = threading.Event()
            main_thread = threading.get_ident()
            worker_threads = []

            def slow_scan(store):
                worker_threads.append(threading.get_ident())
                unblock.wait(3)
                return ScanReport(0, 0, 0, ())

            async with app.run_test(size=(80, 24)) as pilot:
                await app.workers.wait_for_complete()
                with patch("bxvzm.ui.scan_library", side_effect=slow_scan):
                    try:
                        await pilot.press("r", "2")
                        self.assertEqual(app.query_one(TabbedContent).active, "search")
                        self.assertTrue(app._busy)
                    finally:
                        unblock.set()
                    await app.workers.wait_for_complete()
                self.assertTrue(worker_threads)
                self.assertNotIn(main_thread, worker_threads)
