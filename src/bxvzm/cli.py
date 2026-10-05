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
    parser.add_argument(
        "--scan", action="store_true", help="index audio in music/ without opening the TUI"
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--song", metavar="QUERY", help="fuzzy-find and play a local song")
    actions.add_argument("--daemon", action="store_true", help="start the background tray service")
    actions.add_argument("--status", action="store_true", help="show background playback status")
    actions.add_argument("--stop-service", action="store_true", help="exit the background service")
    actions.add_argument("--pause", action="store_true", help="toggle background play/pause")
    actions.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--match", type=int, metavar="N", help="play candidate N for --song")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service_action = any(
        (args.song is not None, args.daemon, args.status, args.stop_service, args.pause, args.serve)
    )
    if (args.check or args.scan) and service_action:
        build_parser().error("--check/--scan cannot be combined with playback/service commands")
    if args.match is not None and (args.song is None or not 1 <= args.match <= 5):
        build_parser().error("--match requires --song and a candidate number from 1 to 5")
    try:
        # Import before touching user data if the interactive dependencies are missing.
        if not args.check and not args.scan and not service_action:
            from bxvzm.ui import MusicApp

        settings = load_settings(args.library, args.config)
        layout = LibraryLayout.at(settings.library_root, settings.app_root)
        store = LibraryStore(layout)
        schema = store.initialize()
        if args.library is not None and not args.serve:
            save_settings(settings)
        if service_action:
            from bxvzm.service import request, serve, start_service

            if args.serve:
                return serve(settings)
            if args.song is not None:
                from bxvzm.search import find_songs

                matches = find_songs(store.list_tracks(), args.song)
                if not matches:
                    print("No local match. Copy music into music/ and run --scan first.")
                    return 1
                if args.match is None and (
                    matches[0].score < 0.7
                    or (len(matches) > 1 and matches[0].score - matches[1].score < 0.08)
                ):
                    print("Choose a match with --song QUERY --match N:")
                    for index, match in enumerate(matches, 1):
                        print(
                            f"{index}. {match.track.title} - {match.track.artist} "
                            f"[{match.track.album}] ({match.track.relative_path})"
                        )
                    return 2
                selected = (args.match or 1) - 1
                if selected >= len(matches):
                    print("That candidate is not in the results.", file=sys.stderr)
                    return 1
                track = matches[selected].track
                start_service(settings)
                request(layout, "play", path=track.relative_path)
                print(f"Playing: {track.title} - {track.artist}")
            elif args.daemon:
                start_service(settings)
                print(
                    "bXVzaVM background service is running. Exit from the tray or --stop-service."
                )
            elif args.stop_service:
                request(layout, "exit")
                print("bXVzaVM background service is exiting.")
            else:
                values = request(layout, "pause" if args.pause else "status")
                state = "Stopped" if values["idle"] else "Paused" if values["paused"] else "Playing"
                print(
                    f"{state}: {values['title']} - {values['artist']} "
                    f"| {int(values['position'])}s | Volume {values['volume']:g}"
                )
        elif args.scan:
            from bxvzm.indexing import scan_library

            report = scan_library(store)
            print(
                f"Indexed: {report.indexed}\nUnavailable: {report.missing}\n"
                f"Duplicate files: {report.duplicate_files}\nIssues: {len(report.issues)}"
            )
            for issue in report.issues:
                print(f"{issue.path}: {issue.reason}")
            return 1 if report.issues else 0
        elif args.check:
            print(f"Library: {layout.root}\nSQLite schema: {schema}\nLibrary is ready.")
        else:
            MusicApp(layout, settings).run()
    except ModuleNotFoundError as error:
        print(
            f"Missing dependency {error.name!r}. Activate .venv and install the locked "
            "requirements, then run python -m pip install -e . --no-deps.",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError, sqlite3.Error, DatabaseVersionError, RuntimeError) as error:
        print(f"Cannot open library: {error}", file=sys.stderr)
        return 1
    return 0
