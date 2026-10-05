import tempfile
import unittest
from pathlib import Path

from bxvzm.library import LibraryLayout


class LibraryPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.layout = LibraryLayout.at(self.base / "data" / "library", app_root=self.base)

    def test_absolute_and_traversal_paths_are_rejected_on_any_os(self) -> None:
        invalid = (
            "",
            ".",
            "../outside",
            "music/../../outside",
            "/outside",
            "C:/outside",
            "C:outside",
            "\\\\server\\share\\file",
            "music\\..\\outside",
            "music/track:stream",
            "music/track\x00",
        )
        for relative in invalid:
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                self.layout.resolve_relative(relative)

    def test_relative_paths_use_forward_slashes(self) -> None:
        asset = self.layout.music / "Artist" / "Album" / "01 - Track.fixture"
        self.assertEqual(self.layout.relative_path(asset), "music/Artist/Album/01 - Track.fixture")
        self.assertEqual(self.layout.resolve_relative(self.layout.relative_path(asset)), asset)

    def test_external_file_cannot_be_serialized(self) -> None:
        with self.assertRaises(ValueError):
            self.layout.relative_path(self.base / "outside")

    def test_symlink_escape_is_rejected_before_library_writes(self) -> None:
        self.layout.root.mkdir(parents=True)
        outside = self.base / "outside"
        outside.mkdir()
        try:
            self.layout.music.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Symlink creation unavailable: {error}")
        with self.assertRaises(ValueError):
            self.layout.initialize()
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse(self.layout.staging.exists())
