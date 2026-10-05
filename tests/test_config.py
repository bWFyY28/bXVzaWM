import json
import shutil
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
        self.config = self.base / "data" / "config.json"

    def test_selection_is_saved_as_a_relative_path(self) -> None:
        settings = load_settings(Path("data/library"), self.config, environ={}, app_root=self.base)
        save_settings(settings)
        self.assertEqual(
            load_settings(config_file=self.config, environ={}, app_root=self.base), settings
        )
        self.assertEqual(json.loads(self.config.read_text())["library_root"], "data/library")
        self.assertFalse(settings.library_root.exists())

    def test_cli_and_environment_override_saved_selection_without_changing_it(self) -> None:
        saved = Settings(self.base / "data" / "saved", self.config, self.base)
        save_settings(saved)
        env = {"BXVZM_LIBRARY": "data/environment"}
        self.assertEqual(
            load_settings(config_file=self.config, environ=env, app_root=self.base).library_root,
            self.base / "data" / "environment",
        )
        self.assertEqual(
            load_settings(
                Path("data/cli"), self.config, environ=env, app_root=self.base
            ).library_root,
            self.base / "data" / "cli",
        )
        self.assertEqual(
            load_settings(config_file=self.config, environ={}, app_root=self.base), saved
        )

    def test_explicit_selection_can_repair_invalid_saved_preferences(self) -> None:
        self.config.parent.mkdir()
        self.config.write_text("not JSON", encoding="utf-8")
        with self.assertRaises(ConfigurationError):
            load_settings(config_file=self.config, environ={}, app_root=self.base)
        repaired = load_settings(Path("data/library"), self.config, environ={}, app_root=self.base)
        save_settings(repaired)
        self.assertEqual(
            load_settings(config_file=self.config, environ={}, app_root=self.base), repaired
        )

    def test_invalid_saved_formats_are_reported(self) -> None:
        self.config.parent.mkdir()
        for payload in (
            [],
            {"version": 2, "library_root": str(self.base)},
            {"version": 1},
            {"version": 1, "library_root": ""},
            {"version": 1, "library_root": "relative/path"},
            {"version": 1, "library_root": str(self.base / "data" / "library")},
            {"version": 1, "library_root": "data/../../outside"},
            {"version": 1, "library_root": "C:/outside"},
        ):
            with self.subTest(payload=payload):
                self.config.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(ConfigurationError):
                    load_settings(config_file=self.config, environ={}, app_root=self.base)

    def test_empty_environment_selection_is_rejected(self) -> None:
        with self.assertRaises(ConfigurationError):
            load_settings(
                config_file=self.config, environ={"BXVZM_LIBRARY": " "}, app_root=self.base
            )

    def test_storage_cannot_escape_the_bundles_data_folder(self) -> None:
        for root in (self.base, self.base / "src", self.base.parent / "outside"):
            with self.subTest(root=root), self.assertRaises(ConfigurationError):
                validate_library_root(root, self.base)
        with self.assertRaises(ConfigurationError):
            load_settings(config_file=self.base / "outside.json", app_root=self.base)

    def test_existing_file_cannot_be_a_library(self) -> None:
        self.config.parent.mkdir()
        existing = self.base / "data" / "file"
        existing.touch()
        with self.assertRaises(ConfigurationError):
            validate_library_root(existing, self.base)

    def test_defaults_ignore_appdata_home_and_working_directory(self) -> None:
        env = {"LOCALAPPDATA": "elsewhere", "APPDATA": "elsewhere", "XDG_CONFIG_HOME": "elsewhere"}
        settings = load_settings(environ=env, app_root=self.base)
        self.assertEqual(settings.library_root, self.base / "data" / "library")
        self.assertEqual(settings.config_file, self.config)
        self.assertEqual(list(self.base.iterdir()), [])

    def test_moving_bundle_preserves_preferences_without_absolute_paths(self) -> None:
        original = self.base / "original"
        settings = load_settings(Path("data/custom"), environ={}, app_root=original)
        save_settings(settings)
        relocated = self.base / "relocated"
        shutil.copytree(original, relocated)
        reopened = load_settings(environ={}, app_root=relocated)
        self.assertEqual(reopened.library_root, relocated / "data" / "custom")
        self.assertNotIn(str(original), reopened.config_file.read_text())
