"""Set up bXVzaVM using installed Python 3.13 on Windows, Linux, or macOS."""

import argparse
import os
import subprocess
import sys
import venv
from pathlib import Path


def environment_python(root: Path) -> Path:
    relative = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    return root / ".venv" / relative


def setup_environment(root: Path) -> dict[str, str]:
    """Keep package downloads, build files, and Python caches inside the bundle."""
    temporary = root / "data" / ".setup-tmp"
    if not temporary.resolve().is_relative_to(root / "data"):
        raise ValueError("Setup temporary files must stay inside data/.")
    temporary.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        TEMP=str(temporary),
        TMP=str(temporary),
        TMPDIR=str(temporary),
        PYTHONDONTWRITEBYTECODE="1",
        PIP_NO_CACHE_DIR="1",
        PIP_DISABLE_PIP_VERSION_CHECK="1",
    )
    # Do not let source metadata shadow the installed package during pip upgrades.
    env.pop("PYTHONPATH", None)
    return env


def prepare_venv(root: Path, env: dict[str, str], recreate: bool = False) -> Path:
    directory = root / ".venv"
    # Verify the absolute deletion target before letting venv clear an old environment.
    if directory.resolve() != root / ".venv":
        raise ValueError(".venv must be a real directory inside the application folder.")
    exists = directory.exists()
    if exists and not (directory / "pyvenv.cfg").is_file():
        raise ValueError("Existing .venv is not a recognized virtual environment; rename it first.")
    executable = environment_python(root)
    usable = False
    if executable.is_file():
        try:
            usable = (
                subprocess.run(
                    [
                        str(executable),
                        "-c",
                        "import sys; sys.exit(sys.version_info[:2] != (3, 13))",
                    ],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                ).returncode
                == 0
            )
        except OSError:
            pass
    if recreate or not usable:
        if Path(sys.prefix).resolve() == directory:
            raise ValueError("Recreate .venv using installed Python, not the environment's Python.")
        print("Creating local .venv (your data and settings are preserved).", flush=True)
        venv.EnvBuilder(with_pip=False, clear=exists).create(directory)
        subprocess.run([str(executable), "-m", "ensurepip", "--upgrade"], env=env, check=True)
    return executable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install bXVzaVM inside this folder")
    parser.add_argument("--dev", action="store_true", help="also install pytest and Ruff")
    parser.add_argument("--recreate", action="store_true", help="rebuild .venv, preserving data/")
    args = parser.parse_args(argv)
    if sys.version_info[:2] != (3, 13):
        print("Run this installer with Python 3.13: py -3.13 install.py or python3.13 install.py.")
        return 1
    root = Path(__file__).resolve().parent
    try:
        env = setup_environment(root)
        executable = prepare_venv(root, env, args.recreate)
        requirements = (
            ["-r", "requirements/dev.txt"]
            if args.dev
            else ["-r", "requirements/runtime.txt", "-r", "requirements/build.txt"]
        )
        commands = (
            ["-m", "pip", "install", *requirements],
            [
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--no-build-isolation",
                "-e",
                ".[dev]" if args.dev else ".",
            ],
            ["-m", "pip", "check"],
            ["-m", "bxvzm", "--check"],
        )
        for command in commands:
            subprocess.run([str(executable), *command], cwd=root, env=env, check=True)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(
            f"Setup failed: {error}\nFix the reported issue and rerun install.py.", file=sys.stderr
        )
        return 1
    print("\nSetup complete. Start the app with: python run.py", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
