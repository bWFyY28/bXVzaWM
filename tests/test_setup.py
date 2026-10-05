import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import install
import run


class SetupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_environment_keeps_temporary_files_and_caches_in_bundle(self) -> None:
        env = install.setup_environment(self.root)
        for key in ("TEMP", "TMP", "TMPDIR"):
            self.assertTrue(Path(env[key]).is_relative_to(self.root / "data"))
        self.assertEqual(env["PIP_NO_CACHE_DIR"], "1")
        self.assertNotIn("PYTHONPATH", env)

    def test_recreating_venv_preserves_preferences_and_audio(self) -> None:
        data = self.root / "data"
        data.mkdir()
        preferences = data / "config.json"
        preferences.write_text(json.dumps({"version": 1, "library_root": "data/library"}))
        audio = data / "track.fixture"
        audio.write_bytes(b"original bytes")
        env = install.setup_environment(self.root)
        with redirect_stdout(io.StringIO()):
            executable = install.prepare_venv(self.root, env)
            install.prepare_venv(self.root, env, recreate=True)
        result = subprocess.run(
            [str(executable), "-c", "import sys; print(sys.prefix)"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(Path(result.stdout.strip()), self.root / ".venv")
        self.assertEqual(audio.read_bytes(), b"original bytes")
        self.assertEqual(json.loads(preferences.read_text())["library_root"], "data/library")

    def test_unrecognized_venv_is_not_deleted(self) -> None:
        directory = self.root / ".venv"
        directory.mkdir()
        sentinel = directory / "keep.txt"
        sentinel.write_text("keep me")
        with self.assertRaises(ValueError):
            install.prepare_venv(self.root, install.setup_environment(self.root), recreate=True)
        self.assertEqual(sentinel.read_text(), "keep me")

    def test_failed_dependency_install_does_not_report_success(self) -> None:
        with (
            patch.object(install, "__file__", str(self.root / "install.py")),
            patch.object(install, "prepare_venv", return_value=Path("local-python")),
            patch.object(
                install.subprocess,
                "run",
                side_effect=subprocess.CalledProcessError(1, "pip"),
            ),
            redirect_stdout(io.StringIO()) as output,
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(install.main([]), 1)
        self.assertNotIn("Setup complete", output.getvalue())
        self.assertFalse((self.root / "data" / "library").exists())

    def test_launcher_reports_missing_setup_and_passes_arguments(self) -> None:
        with patch.object(run, "__file__", str(self.root / "run.py")):
            with redirect_stderr(io.StringIO()):
                self.assertEqual(run.main(["--check"]), 1)
            executable = install.environment_python(self.root)
            executable.parent.mkdir(parents=True)
            executable.touch()
            with patch.object(run.subprocess, "run") as process:
                process.return_value.returncode = 7
                self.assertEqual(run.main(["--library", "data/custom", "--check"]), 7)
            self.assertEqual(process.call_args.kwargs["cwd"], self.root)
            self.assertEqual(
                process.call_args.args[0],
                [str(executable), "-m", "bxvzm", "--library", "data/custom", "--check"],
            )
