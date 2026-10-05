import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bxvzm.cli import main


class CommandLineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "library"
        self.config = self.base / "preferences.json"

    def test_check_initializes_and_remembers_selection_without_ui(self) -> None:
        with redirect_stdout(io.StringIO()) as output:
            result = main(["--library", str(self.root), "--config", str(self.config), "--check"])
        self.assertEqual(result, 0)
        self.assertIn("SQLite schema: 1", output.getvalue())
        self.assertTrue((self.root / "library.sqlite3").is_file())
        self.assertEqual(json.loads(self.config.read_text())["library_root"], str(self.root))
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--config", str(self.config), "--check"]), 0)
        self.assertIn(str(self.root), output.getvalue())

    def test_invalid_root_returns_error_without_saving_selection(self) -> None:
        self.root.touch()
        with redirect_stderr(io.StringIO()) as output:
            result = main(["--library", str(self.root), "--config", str(self.config), "--check"])
        self.assertEqual(result, 1)
        self.assertIn("Cannot open library", output.getvalue())
        self.assertFalse(self.config.exists())

