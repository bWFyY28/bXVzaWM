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
    parser.add_argument("command", nargs="?", choices=("open",), help="open the interface")
    parser.add_argument("view", nargs="?", choices=("tui",), help="terminal interface")
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
    actions.add_argument(
        "--search", metavar="QUERY", help="find a song on Amazon Music in your browser"
    )
    actions.add_argument("--daemon", action="store_true", help="start the background tray service")
    actions.add_argument("--status", action="store_true", help="show background playback status")
    actions.add_argument("--stop-service", action="store_true", help="exit the background service")
    actions.add_argument("--pause", action="store_true", help="toggle background play/pause")
    actions.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)
    actions.add_argument("--download", metavar="URL", help="prepare a manual DoubleDouble handoff")
    actions.add_argument(
        "--download-copied",
        action="store_true",
        help="use a copied Amazon Music link (native Windows)",
    )
    actions.add_argument(
        "--import",
        dest="import_source",
        type=Path,
        metavar="PATH",
        help="stage a downloaded ZIP, audio file, or folder for review",
    )
    actions.add_argument("--imports", action="store_true", help="list import jobs and their states")
    actions.add_argument(
        "--review-import", metavar="JOB", help="show a staged import's files/evidence"
    )
    actions.add_argument("--accept-import", metavar="JOB", help="accept or resume an import")
    actions.add_argument(
        "--discard-import", metavar="JOB", help="discard an uncommitted staged job"
    )
    parser.add_argument(
        "--open-browser", action="store_true", help="open a prefilled DoubleDouble page"
    )
    parser.add_argument(
        "--source-url", default="", metavar="URL", help="record provider evidence with --import"
    )
    parser.add_argument(
        "--accept-unverified",
        action="store_true",
        help="explicitly accept unknown completeness/edition",
    )
    parser.add_argument("--match", type=int, metavar="N", help="play candidate N for --song")
    parser.add_argument("--result", type=int, metavar="N", help="select result N with --search")
    parser.add_argument(
        "--provider", choices=("amazon", "deezer"), help="search source; default: amazon (browser)"
    )
    parser.add_argument(
        "--track-link", action="store_true", help="use the selected track rather than its album"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    service_action = any(
        (args.song is not None, args.daemon, args.status, args.stop_service, args.pause, args.serve)
    )
    transfer_action = any(
        (
            args.download is not None,
            args.download_copied,
            args.search is not None,
            args.import_source is not None,
            args.imports,
            args.review_import,
            args.accept_import,
            args.discard_import,
        )
    )
    if args.command and (
        args.view != "tui" or service_action or transfer_action or args.check or args.scan
    ):
        build_parser().error("use 'open tui' without another action")
    if (args.check or args.scan) and (service_action or transfer_action):
        build_parser().error("--check/--scan cannot be combined with other actions")
    provider = args.provider or "amazon"
    if args.provider and args.search is None:
        build_parser().error("--provider requires --search")
    if provider == "amazon" and (args.result is not None or args.track_link):
        build_parser().error(
            "Amazon search uses your browser; --result/--track-link require --provider deezer"
        )
    if (
        args.open_browser
        and args.download is None
        and not args.download_copied
        and not (args.search is not None and (provider == "amazon" or args.result is not None))
    ):
        build_parser().error("--open-browser requires a download link or selected search")
    if args.result is not None and (args.search is None or not 1 <= args.result <= 20):
        build_parser().error("--result requires --search and a number from 1 to 20")
    if args.track_link and (args.search is None or args.result is None):
        build_parser().error("--track-link requires --search with --result")
    if args.source_url and args.import_source is None:
        build_parser().error("--source-url requires --import")
    if args.accept_unverified and args.accept_import is None:
        build_parser().error("--accept-unverified requires --accept-import")
    if args.match is not None and (args.song is None or not 1 <= args.match <= 5):
        build_parser().error("--match requires --song and a candidate number from 1 to 5")
    try:
        # Import before touching user data if the interactive dependencies are missing.
        if not args.check and not args.scan and not service_action and not transfer_action:
            from bxvzm.ui import MusicApp

        settings = load_settings(args.library, args.config)
        layout = LibraryLayout.at(settings.library_root, settings.app_root)
        store = LibraryStore(layout)
        schema = store.initialize()
        if args.library is not None and not args.serve:
            save_settings(settings)
        if transfer_action:
            from bxvzm.transfers.imports import accept_import, discard_import, stage_import
            from bxvzm.transfers.links import (
                download_page_url,
                open_download_page,
                validate_provider_url,
            )

            if args.search is not None and provider == "amazon":
                from bxvzm.catalog.amazon import open_search, search_url

                print(
                    f"Amazon Music search: {search_url(args.search)}\n"
                    "Choose an album in the browser and copy its Share link.\n"
                    "Then: bxvzm --download-copied --open-browser (native Windows).\n"
                    "Automatic Amazon catalog results need approved API access."
                )
                if args.open_browser:
                    open_search(args.search)
            elif args.search is not None:
                from bxvzm.catalog.deezer import search_songs

                songs = search_songs(args.search)
                if not songs:
                    print("No catalog results. Try the song's full title and artist.")
                    return 1
                if args.result is None:
                    for index, song in enumerate(songs, 1):
                        status = (
                            "unknown" if song.explicit is None else "yes" if song.explicit else "no"
                        )
                        print(
                            f"{index}. {song.title} - {song.artist} [{song.album}] "
                            f"| Deezer | Explicit (track): {status}\nAlbum: {song.album_url}"
                        )
                    print(
                        "Choose with --provider deezer --search QUERY --result N; "
                        "add --open-browser for the prefilled handoff."
                    )
                    return 0
                if args.result > len(songs):
                    print("That result is not in the catalog response.", file=sys.stderr)
                    return 1
                song = songs[args.result - 1]
                url = song.track_url if args.track_link else song.album_url
                link = validate_provider_url(url)
                print(
                    f"Selected: {song.title} - {song.artist} [{song.album}]\n{url}\n"
                    f"DoubleDouble: {download_page_url(link)}\n"
                    "Complete CAPTCHA/download in the browser."
                )
                if args.open_browser:
                    open_download_page(link)
            elif args.download is not None or args.download_copied:
                if args.download_copied:
                    from bxvzm.transfers.clipboard import copied_amazon_link

                    link = copied_amazon_link()
                else:
                    link = validate_provider_url(args.download)
                print(
                    f"{link.provider} {link.kind}: {link.url}\n"
                    f"Open {download_page_url(link)}; its URL input is prefilled.\n"
                    "Complete CAPTCHA and download manually in the browser.\n"
                    "Then use --import PATH to stage the downloaded audio."
                )
                if args.open_browser:
                    open_download_page(link)
            elif args.import_source is not None:
                job = stage_import(store, args.import_source, args.source_url)
                print(
                    f"Import staged: {job['job_id']}\n"
                    f"Files: {len(job['manifest']['files'])}\n"
                    "Completeness: unknown | Edition: unknown\n"
                    f"Review with --review-import {job['job_id']}"
                )
            elif args.imports:
                for job in store.list_imports():
                    print(
                        f"{job['job_id']} | {job['state']} | "
                        f"{len(job['manifest']['files'])} files | {job['manifest']['source']}"
                    )
            elif args.review_import:
                import json

                print(
                    json.dumps(store.get_import(args.review_import), indent=2, ensure_ascii=False)
                )
            elif args.accept_import:
                count = accept_import(
                    store, args.accept_import, accept_unverified=args.accept_unverified
                )
                print(f"Accepted {count} files as unverified. No source files were removed.")
            else:
                discard_import(store, args.discard_import)
                print("Staged import discarded. Original source files were preserved.")
        elif service_action:
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
