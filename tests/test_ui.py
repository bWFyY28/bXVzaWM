import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

from bxvzm.library import LibraryLayout

HAS_TEXTUAL = importlib.util.find_spec("textual") is not None


@unittest.skipUnless(HAS_TEXTUAL, "Install locked dependencies to run Textual checks")
class InterfaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_navigation_help_and_layout_at_80_by_24(self) -> None:
        from textual.widgets import Static, TabbedContent

        from bxvzm.ui import HelpScreen, MusicApp

        with tempfile.TemporaryDirectory() as directory:
            layout = LibraryLayout.at(Path(directory) / "library")
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
                await pilot.press("q")
            # UI construction and navigation must not create library data.
            self.assertFalse(layout.root.exists())
