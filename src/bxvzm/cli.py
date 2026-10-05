"""Command-line setup and application launch."""

import argparse
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path

from bxvzm import __version__
from bxvzm.config import load_settings, save_settings
from bxvzm.database import DatabaseVersionError, LibraryStore
from bxvzm.library import LibraryLayout


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="bXVzaVM local music library")
    parser.add_argument("--version", action="version", version=f"bXVzaVM {__version__}")
    parser.add_argument(
        "--library", type=Path, help="select a library inside the bundle's data folder"
    )
    parser.add_argument(
        "--config", type=Path, help="select a preferences file inside the data folder"
    )
    parser.add_argument(
        "--check", action="store_true", help="initialize/check the library without opening the TUI"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        # Import before touching user data if the interactive dependencies are missing.
        if not args.check:
            from bxvzm.ui import MusicApp

        settings = load_settings(args.library, args.config)
        layout = LibraryLayout.at(settings.library_root, settings.app_root)
        schema = LibraryStore(layout).initialize()
        if args.library is not None:
            save_settings(settings)
        if args.check:
            print(f"Library: {layout.root}\nSQLite schema: {schema}\nLibrary is ready.")
        else:
            MusicApp(layout).run()
    except ModuleNotFoundError as error:
        print(
            f"Missing dependency {error.name!r}. Activate .venv and install the locked "
            "requirements, then run python -m pip install -e . --no-deps.",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError, sqlite3.Error, DatabaseVersionError) as error:
        print(f"Cannot open library: {error}", file=sys.stderr)
        return 1
    return 0
