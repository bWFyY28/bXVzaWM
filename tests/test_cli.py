import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from bxvzm.cli import main


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
        self.assertIn("SQLite schema: 1", output.getvalue())
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
