"""Text-first local music browser; disk I/O runs in a worker."""

import sqlite3
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import DataTable, Footer, Input, Static, TabbedContent, TabPane, Tabs

from bxvzm.config import Settings
from bxvzm.database import LibraryStore
from bxvzm.indexing import ScanReport, scan_library
from bxvzm.library import LibraryLayout
from bxvzm.metadata import Track
from bxvzm.search import find_songs
from bxvzm.service import request, start_service
from bxvzm.ui.catalog import CatalogPanel
from bxvzm.ui.transfers import ImportPanel


class HelpScreen(ModalScreen[None]):
    BINDINGS = [("escape", "dismiss", "Close"), ("question_mark", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        yield Static(
            "bXVzaVM\n\n"
            "1-5  Switch views\n"
            "Tab / Shift+Tab  Move focus\n"
            "Arrow keys / j / k  Navigate tracks\n"
            "/  Filter library    r  Rescan music/\n"
            "f  Toggle selected track's favorite\n"
            "?  Help    q  Quit\n\n"
            "Enter  Play    Space  Pause/resume\n"
            "h / l  Seek -/+5s    - / +  Volume\n"
            "q closes the TUI; the tray keeps playing.\n"
            "Esc  Close this help",
            id="help-dialog",
        )


class MusicApp(App[None]):
    TITLE = "bXVzaVM"
    CSS_PATH = Path(__file__).resolve().parents[1] / "themes/gruvbox.tcss"
    ENABLE_COMMAND_PALETTE = False
    AUTO_FOCUS = "#tracks"
    BINDINGS = [
        Binding("1", "view('library')", "Library", show=False),
        Binding("2", "view('search')", "Search", show=False),
        Binding("3", "view('favorites')", "Favorites", show=False),
        Binding("4", "view('playlists')", "Playlists", show=False),
        Binding("5", "view('imports')", "Imports", show=False),
        Binding("slash", "filter", "Filter"),
        Binding("r", "scan", "Rescan"),
        Binding("f", "favorite", "Favorite"),
        Binding("j", "track_down", "Down", show=False),
        Binding("k", "track_up", "Up", show=False),
        Binding("space", "pause", "Pause", show=False),
        Binding("h", "seek(-5)", "Seek back", show=False),
        Binding("l", "seek(5)", "Seek forward", show=False),
        Binding("minus", "volume(-5)", "Quieter", show=False),
        Binding("plus,equal", "volume(5)", "Louder", show=False),
        Binding("escape", "leave_filter", "Tracks", show=False),
        Binding("question_mark", "help", "Help"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, layout: LibraryLayout, settings: Settings | None = None) -> None:
        super().__init__()
        self.layout = layout
        self.store = LibraryStore(layout)
        self.settings = settings
        self._player_busy = False
        self._connected = False
        self._volume = 75.0
        self.tracks: list[Track] = []
        self._busy = False
        self.animation_level = "none"
        self.register_theme(
            Theme(
                name="bxvzm-gruvbox",
                primary="#7daea3",
                secondary="#89b482",
                accent="#7daea3",
                foreground="#d4be98",
                background="#282828",
                surface="#32302f",
                panel="#32302f",
                dark=True,
            )
        )
        self.theme = "bxvzm-gruvbox"

    def compose(self) -> ComposeResult:
        yield Static("bXVzaVM | Local music", id="title")
        with TabbedContent(initial="library", id="views"):
            with TabPane("Library", id="library"):
                yield Input(placeholder="Filter title, artist, album, or path", id="filter")
                yield DataTable(id="tracks", cursor_type="row", zebra_stripes=False)
                yield Static("Copy audio into music/, then press r to scan.", id="library-status")
                yield Static(str(self.layout.music), id="library-root", markup=False)
            with TabPane("Search", id="search"):
                yield CatalogPanel()
            with TabPane("Favorites", id="favorites"):
                yield DataTable(id="favorite-tracks", cursor_type="row", zebra_stripes=False)
                yield Static(
                    "Press f on a track to add or remove a favorite.", classes="empty-state"
                )
            with TabPane("Playlists", id="playlists"):
                yield Static("Playlist editing is upcoming.", classes="empty-state")
            with TabPane("Imports", id="imports"):
                yield ImportPanel(self.store)
        yield Static("Stopped | No track loaded | Enter Play / Space Pause", id="player")
        yield Footer()

    def on_mount(self) -> None:
        for table in self.query(DataTable):
            if table.id not in ("tracks", "favorite-tracks"):
                continue
            table.add_columns(
                "Fav", "Title", "Artist", "Album", "Disc/Track", "Time", "Format", "File"
            )
        self.query_one("#tracks", DataTable).focus()
        self._busy = True
        self._library_task("load")
        if self.settings is not None:
            self._player_busy = True
            self._player_task("connect")
            self.set_interval(1, self._poll_player)

    @work(thread=True)
    def _library_task(self, operation: str, path: str = "") -> None:
        try:
            report = None
            if operation == "scan":
                self.store.initialize()
                report = scan_library(self.store)
            elif operation == "favorite":
                self.store.toggle_favorite(path)
            if self.layout.database.exists():
                tracks = self.store.list_tracks()
                last_scan = self.store.load_state("last_scan", {})
            else:
                tracks, last_scan = [], {}
            self.call_from_thread(self._loaded, tracks, report, last_scan)
        except (OSError, ValueError, sqlite3.Error, RuntimeError) as error:
            self.call_from_thread(self._failed, str(error))

    def _loaded(self, tracks: list[Track], report: ScanReport | None, last_scan: dict) -> None:
        self.tracks = tracks
        self._busy = False
        self._render_tracks()
        available = sum(track.available for track in tracks)
        missing = len(tracks) - available
        issues = len(report.issues) if report else len(last_scan.get("issues", []))
        duplicates = report.duplicate_files if report else last_scan.get("duplicate_files", 0)
        self.query_one("#library-status", Static).update(
            f"{available} tracks | {missing} unavailable | "
            f"{duplicates} duplicate files | {issues} issues"
        )

    def _failed(self, message: str) -> None:
        self._busy = False
        self.query_one("#library-status", Static).update(Text(f"Library error: {message}"))

    def _render_tracks(self) -> None:
        query = self.query_one("#filter", Input).value.casefold().strip()
        fuzzy_paths = (
            {
                match.track.relative_path
                for match in find_songs(self.tracks, query, len(self.tracks))
            }
            if query
            else set()
        )
        for table_id in ("tracks", "favorite-tracks"):
            table = self.query_one(f"#{table_id}", DataTable)
            selected = (
                table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
                if table.row_count
                else None
            )
            table.clear()
            for track in self.tracks:
                if table_id == "favorite-tracks" and not track.favorite:
                    continue
                if (
                    table_id == "tracks"
                    and query
                    not in " ".join(
                        (track.title, track.artist, track.album, track.relative_path)
                    ).casefold()
                    and track.relative_path not in fuzzy_paths
                ):
                    continue
                seconds = int(track.duration)
                table.add_row(
                    "yes" if track.favorite else "",
                    Text(track.title),
                    Text(track.artist),
                    Text(track.album),
                    f"{track.disc_number or '?'}/{track.track_number or '?'}",
                    f"{seconds // 60}:{seconds % 60:02}",
                    track.format,
                    "ready" if track.available else "missing",
                    key=track.relative_path,
                )
            if selected and any(key.value == selected for key in table.rows):
                table.move_cursor(row=table.get_row_index(selected))

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter":
            self._render_tracks()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "filter":
            self.query_one("#tracks", DataTable).focus()

    def action_view(self, view: str) -> None:
        # Keep focus out of a pane as it is hidden, avoiding automatic refocus
        # on another library child and its resulting TabPane.Focused message.
        self.query_one(Tabs).focus()
        self.query_one("#views", TabbedContent).active = view
        if view in ("library", "favorites"):
            table_id = "#tracks" if view == "library" else "#favorite-tracks"
            self.query_one(table_id, DataTable).focus()

    def action_filter(self) -> None:
        self.action_view("library")
        self.query_one("#filter", Input).focus()

    def action_scan(self) -> None:
        if not self._busy:
            self._busy = True
            self.query_one("#library-status", Static).update("Scanning music/...")
            self._library_task("scan")

    def action_favorite(self) -> None:
        if (
            not self._busy
            and isinstance(self.focused, DataTable)
            and self.focused.id in ("tracks", "favorite-tracks")
            and self.focused.row_count
        ):
            key = self.focused.coordinate_to_cell_key(self.focused.cursor_coordinate).row_key.value
            if key is not None:
                self._busy = True
                self._library_task("favorite", key)

    def action_track_down(self) -> None:
        if isinstance(self.focused, DataTable):
            self.focused.action_cursor_down()

    def action_track_up(self) -> None:
        if isinstance(self.focused, DataTable):
            self.focused.action_cursor_up()

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_leave_filter(self) -> None:
        if isinstance(self.focused, Input):
            self.query_one("#tracks", DataTable).focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        path = event.row_key.value
        if path is not None:
            self._send_player("play", path=path)

    def action_pause(self) -> None:
        self._send_player("pause")

    def action_seek(self, seconds: int) -> None:
        self._send_player("seek", seconds=seconds)

    def action_volume(self, amount: int) -> None:
        self._send_player("volume", value=max(0, min(100, self._volume + amount)))

    def _poll_player(self) -> None:
        if self._connected:
            self._send_player("status")

    def _send_player(self, command: str, **arguments) -> None:
        if not self._player_busy and self.settings is not None:
            self._player_busy = True
            self._player_task(command, arguments)

    @work(thread=True)
    def _player_task(self, command: str, arguments: dict | None = None) -> None:
        try:
            assert self.settings is not None
            if command == "connect":
                values = start_service(self.settings)
            else:
                if command == "play":
                    start_service(self.settings)
                values = request(self.layout, command, **(arguments or {}))
            self.call_from_thread(self._player_updated, values)
        except (OSError, ValueError, RuntimeError) as error:
            self.call_from_thread(self._player_failed, str(error))

    def _player_updated(self, values: dict) -> None:
        self._player_busy = False
        self._connected = True
        self._volume = values["volume"]
        state = "Stopped" if values["idle"] else "Paused" if values["paused"] else "Playing"
        seconds = int(values["position"])
        duration = int(values["duration"])
        self.query_one("#player", Static).update(
            Text(
                f"{state} | {values.get('error') or values['title']} - {values['artist']} | "
                f"{seconds // 60}:{seconds % 60:02}/{duration // 60}:{duration % 60:02} | "
                f"Vol {self._volume:g}"
            )
        )

    def _player_failed(self, message: str) -> None:
        self._player_busy = False
        self._connected = False
        self.query_one("#player", Static).update(Text(message))
