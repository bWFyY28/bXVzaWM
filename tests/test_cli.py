import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from helpers import write_wave

from bxvzm.cli import main
from bxvzm.database import SCHEMA_VERSION, LibraryStore
from bxvzm.indexing import scan_library
from bxvzm.library import LibraryLayout


class CommandLineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "data" / "library"
        self.config = self.base / "data" / "config.json"
        bundle_root = patch("bxvzm.config.application_root", return_value=self.base)
        bundle_root.start()
        self.addCleanup(bundle_root.stop)

    def test_check_initializes_and_remembers_selection_without_ui(self) -> None:
        with redirect_stdout(io.StringIO()) as output:
            result = main(["--library", str(self.root), "--config", str(self.config), "--check"])
        self.assertEqual(result, 0)
        self.assertIn(f"SQLite schema: {SCHEMA_VERSION}", output.getvalue())
        self.assertTrue((self.root / "library.sqlite3").is_file())
        self.assertEqual(json.loads(self.config.read_text())["library_root"], "data/library")
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--config", str(self.config), "--check"]), 0)
        self.assertIn(str(self.root), output.getvalue())

    def test_invalid_root_returns_error_without_saving_selection(self) -> None:
        self.root.parent.mkdir(parents=True)
        self.root.touch()
        with redirect_stderr(io.StringIO()) as output:
            result = main(["--library", str(self.root), "--config", str(self.config), "--check"])
        self.assertEqual(result, 1)
        self.assertIn("Cannot open library", output.getvalue())
        self.assertFalse(self.config.exists())

    def test_default_check_uses_bundle_data_folder(self) -> None:
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--check"]), 0)
        self.assertTrue((self.root / "library.sqlite3").exists())
        self.assertEqual([path.name for path in self.base.iterdir()], ["data"])

    def test_external_selection_is_rejected_without_creating_files(self) -> None:
        outside = self.base / "outside"
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--library", str(outside), "--check"]), 1)
        self.assertFalse(outside.exists())
        self.assertFalse(self.config.exists())

    def populate(self, duplicate: bool = False) -> LibraryStore:
        layout = LibraryLayout.at(self.root, app_root=self.base)
        store = LibraryStore(layout)
        store.initialize()
        write_wave(layout.music / "song.wav")
        if duplicate:
            write_wave(layout.music / "another-edition.wav")
        scan_library(store)
        return store

    def test_song_typo_dispatches_to_background_without_tui(self) -> None:
        self.populate()
        with (
            patch("bxvzm.service.start_service") as start,
            patch("bxvzm.service.request") as send,
            redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(main(["--song", "cirle"]), 0)
        start.assert_called_once()
        self.assertEqual(send.call_args.args[1], "play")
        self.assertEqual(send.call_args.kwargs, {"path": "music/song.wav"})
        self.assertIn("Playing: Circles - Post Malone", output.getvalue())

    def test_ambiguous_editions_require_candidate_and_no_match_does_not_start_service(self) -> None:
        self.populate(duplicate=True)
        with (
            patch("bxvzm.service.start_service") as start,
            redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(main(["--song", "cirle"]), 2)
            self.assertIn("--match N", output.getvalue())
            self.assertEqual(main(["--song", "zzzzzzzz"]), 1)
        start.assert_not_called()
        with (
            patch("bxvzm.service.start_service"),
            patch("bxvzm.service.request") as send,
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(main(["--song", "cirle", "--match", "2"]), 0)
        self.assertEqual(send.call_args.kwargs["path"], "music/song.wav")

    def test_cli_scan_reports_corrupt_files(self) -> None:
        self.populate()
        (self.root / "music/broken.mp3").write_bytes(b"broken")
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--scan"]), 1)
        self.assertIn("Indexed: 1", output.getvalue())
        self.assertIn("music/broken.mp3", output.getvalue())

    def test_service_child_does_not_persist_temporary_library_override(self) -> None:
        with patch("bxvzm.service.serve", return_value=0):
            self.assertEqual(main(["--serve", "--library", str(self.root)]), 0)
        self.assertFalse(self.config.exists())
