import json
import tempfile
import unittest
from pathlib import Path

from bxvzm.config import (
    ConfigurationError,
    Settings,
    load_settings,
    save_settings,
    validate_library_root,
)


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.config = self.base / "preferences" / "config.json"

    def test_selection_is_saved_outside_the_portable_library(self) -> None:
        settings = load_settings(self.base / "library", self.config, environ={})
        save_settings(settings)
        self.assertEqual(load_settings(config_file=self.config, environ={}), settings)
        self.assertFalse(settings.library_root.exists())

    def test_cli_and_environment_override_saved_selection_without_changing_it(self) -> None:
        saved = Settings(self.base / "saved", self.config)
        save_settings(saved)
        env = {"BXVZM_LIBRARY": str(self.base / "environment")}
        self.assertEqual(
            load_settings(config_file=self.config, environ=env).library_root,
            self.base / "environment",
        )
        self.assertEqual(
            load_settings(self.base / "cli", self.config, environ=env).library_root,
            self.base / "cli",
        )
        self.assertEqual(load_settings(config_file=self.config, environ={}), saved)

    def test_explicit_selection_can_repair_invalid_saved_preferences(self) -> None:
        self.config.parent.mkdir()
        self.config.write_text("not JSON", encoding="utf-8")
        with self.assertRaises(ConfigurationError):
            load_settings(config_file=self.config, environ={})
        repaired = load_settings(self.base / "library", self.config, environ={})
        save_settings(repaired)
        self.assertEqual(load_settings(config_file=self.config, environ={}), repaired)

    def test_invalid_saved_formats_are_reported(self) -> None:
        self.config.parent.mkdir()
        for payload in (
            [],
            {"version": 2, "library_root": str(self.base)},
            {"version": 1},
            {"version": 1, "library_root": ""},
            {"version": 1, "library_root": "relative/path"},
        ):
            with self.subTest(payload=payload):
                self.config.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(ConfigurationError):
                    load_settings(config_file=self.config, environ={})

    def test_empty_environment_selection_is_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            load_settings(config_file=self.config, environ={"BXVZM_LIBRARY": " "})

    def test_library_cannot_be_inside_checkout(self) -> None:
        checkout = self.base / "checkout"
        for root in (checkout, checkout / "audio"):
            with self.subTest(root=root), self.assertRaises(ConfigurationError):
                validate_library_root(root, checkout)

    def test_existing_file_cannot_be_a_library(self) -> None:
        existing = self.base / "file"
        existing.touch()
        with self.assertRaises(ConfigurationError):
            validate_library_root(existing)

