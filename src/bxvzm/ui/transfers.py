"""Text-only download and import panels; transfer I/O stays in workers."""

import os
import sqlite3
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Collapsible, DataTable, Input, Static

from bxvzm.database import LibraryStore
from bxvzm.transfers.imports import accept_import, discard_import, stage_import
from bxvzm.transfers.links import DOUBLEDOUBLE_URL, open_download_page, validate_provider_url


class DownloadPanel(Vertical):
    def compose(self) -> ComposeResult:
        yield Static("Download from Amazon Music", classes="empty-state")
        yield Input(
            placeholder="Copied Amazon album/track URL, or paste a direct provider link",
            id="download-url",
        )
        with Horizontal(classes="transfer-actions"):
            yield Button("Copy link", id="copy-provider")
            yield Button("Open DoubleDouble", id="open-download")
        yield Static(
            f"DoubleDouble handoff: {DOUBLEDOUBLE_URL}\n"
            "Opening fills the URL input; complete CAPTCHA/download in your browser.\n"
            "Then select the ZIP, file, or folder in Imports.\n"
            "The source link is evidence; it does not verify the album edition.",
            id="download-status",
            markup=False,
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        try:
            link = validate_provider_url(self.query_one("#download-url", Input).value)
            if event.button.id == "copy-provider":
                if os.name == "nt":
                    self._copy_windows(link.url)
                else:
                    self.app.copy_to_clipboard(link.url)
                    self._status(f"Sent to terminal clipboard: {link.url}")
            else:
                self._open(link.url)
        except ValueError as error:
            self.query_one("#download-status", Static).update(Text(str(error)))

    @work(thread=True)
    def _copy_windows(self, url: str) -> None:
        import pywintypes
        import win32clipboard

        try:
            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(url, win32clipboard.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
            message = f"Copied: {url}"
        except pywintypes.error as error:
            message = f"Clipboard unavailable: {error}. Copy this link manually: {url}"
        self.app.call_from_thread(self._status, message)

    @work(thread=True)
    def _open(self, url: str) -> None:
        try:
            open_download_page(validate_provider_url(url))
            message = (
                "DoubleDouble opened with the URL filled in. "
                "Complete CAPTCHA/download in the browser."
            )
        except (OSError, RuntimeError, ValueError) as error:
            message = str(error)
        self.app.call_from_thread(self._status, message)

    def _status(self, message: str) -> None:
        self.query_one("#download-status", Static).update(Text(message))


class ImportPanel(VerticalScroll):
    def __init__(self, store: LibraryStore) -> None:
        super().__init__()
        self.store = store
        self.jobs: dict[str, dict] = {}
        self.selected = ""
        self.busy = False

    def compose(self) -> ComposeResult:
        yield Static(
            "Choose a download > Review files > Add to library",
            id="import-intro",
        )
        with Horizontal(classes="transfer-actions"):
            yield Input(
                placeholder="Downloaded ZIP, audio file or folder path",
                id="import-path",
            )
            yield Button("Review files", id="stage-import")
        yield Static("Your original download stays untouched.", id="import-status", markup=False)
        yield Static(
            "No download selected yet. Nothing has been added to your library.",
            id="import-detail",
            markup=False,
        )
        yield Checkbox(
            "I checked these files; add without album verification",
            id="confirm-import",
            disabled=True,
        )
        with Horizontal(classes="transfer-actions"):
            yield Button("Add to library", id="accept-import", disabled=True)
            yield Button("Cancel review", id="discard-import", disabled=True)
        with Collapsible(
            title="Files in this download",
            collapsed=True,
            id="import-files-section",
            collapsed_symbol="+",
            expanded_symbol="-",
        ):
            yield DataTable(id="import-files", cursor_type="row", zebra_stripes=False)
            yield Static(
                "Select a file for its original name and audio details.",
                id="import-file-detail",
                markup=False,
            )
        with Collapsible(
            title="Album link (optional)", collapsed=True, collapsed_symbol="+", expanded_symbol="-"
        ):
            yield Input(placeholder="Amazon Music album link for this download", id="import-source")
        with Collapsible(
            title="Previous downloads", collapsed=True, collapsed_symbol="+", expanded_symbol="-"
        ):
            yield DataTable(id="import-jobs", cursor_type="row", zebra_stripes=False)
            with Horizontal(classes="transfer-actions"):
                yield Button("Refresh history", id="refresh-imports")

    def on_mount(self) -> None:
        self.query_one("#import-jobs", DataTable).add_columns("Download", "Status", "Files")
        self.query_one("#import-files", DataTable).add_columns(
            "Title", "Artist", "Disc / Track", "Format"
        )
        self._run("load")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if self.busy:
            return
        action = {
            "stage-import": "stage",
            "refresh-imports": "load",
            "accept-import": "accept",
            "discard-import": "discard",
        }.get(event.button.id or "")
        if action:
            source = self.query_one("#import-path", Input).value.strip().strip('"')
            if action == "stage" and not source:
                self.query_one("#import-status", Static).update(
                    "Paste the path to a downloaded ZIP, audio file or folder first."
                )
                return
            self.busy = True
            for button in self.query(Button):
                button.disabled = True
            self.query_one("#confirm-import", Checkbox).disabled = True
            self.query_one("#import-status", Static).update(
                {
                    "stage": "Reading your download. No files are added to the library yet...",
                    "accept": "Adding original audio to your library...",
                    "discard": "Removing review copies. Your original download stays untouched...",
                    "load": "Loading previous downloads...",
                }[action]
            )
            url = self.query_one("#import-source", Input).value.strip() if action == "stage" else ""
            self._run(action, source, url, self.selected)

    @work(thread=True)
    def _run(self, action: str, source: str = "", url: str = "", job_id: str = "") -> None:
        message = ""
        try:
            if action != "load":
                self.store.initialize()
            if action == "stage":
                job = stage_import(self.store, Path(source), url)
                job_id = job["job_id"]
            elif action == "accept":
                count = accept_import(self.store, job_id, accept_unverified=True)
                message = (
                    f"Added {count} files to your library. Your original download is preserved."
                )
            elif action == "discard":
                discard_import(self.store, job_id)
                message = "Review cancelled. Your original download is preserved."
            jobs = self.store.list_imports() if self.store.layout.database.exists() else []
            self.app.call_from_thread(self._loaded, jobs, job_id, message, action == "accept")
        except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
            try:
                jobs = self.store.list_imports() if self.store.layout.database.exists() else []
            except (OSError, ValueError, RuntimeError, sqlite3.Error):
                jobs = []
            self.app.call_from_thread(self._loaded, jobs, job_id, str(error), False)

    def _loaded(self, jobs: list[dict], selected: str, message: str, accepted: bool) -> None:
        self.busy = False
        self.jobs = {job["job_id"]: job for job in jobs}
        self.query_one("#confirm-import", Checkbox).value = False
        table = self.query_one("#import-jobs", DataTable)
        table.clear()
        for job in jobs:
            table.add_row(
                Text(Path(job["manifest"]["source"]).name),
                self._state_label(job["state"]),
                str(len(job["manifest"]["files"])),
                key=job["job_id"],
            )
        self.query_one("#stage-import", Button).disabled = False
        self.query_one("#refresh-imports", Button).disabled = False
        self.selected = selected if selected in self.jobs else next(iter(self.jobs), "")
        if self.selected:
            table.move_cursor(row=table.get_row_index(self.selected))
        self._review()
        if selected and selected in self.jobs and self.jobs[selected]["state"] == "review":
            self.query_one("#import-files-section", Collapsible).collapsed = False
        if selected:
            self.call_after_refresh(self.scroll_home, animate=False)
        if message:
            self.query_one("#import-status", Static).update(Text(message))
        else:
            self.query_one("#import-status", Static).update(
                "Your original download stays untouched."
            )
        if accepted:
            self.app.action_scan()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        if event.data_table.id == "import-files":
            job = self.jobs.get(self.selected)
            if job and event.row_key.value is not None:
                files = job["manifest"]["files"]
                index = int(event.row_key.value)
                if index < len(files):
                    file = files[index]
                    track = file["track"]
                    self.query_one("#import-file-detail", Static).update(
                        Text(
                            f"{file['source_name']}\n"
                            f"{track['duration']:.1f}s | "
                            f"{track['sample_rate'] or '?'} Hz | "
                            f"{track['bits_per_sample'] or '?'} bit"
                        )
                    )
        elif event.row_key.value in self.jobs:
            # Rebuilding history queues highlights for its first row before the
            # selected download is restored. Ignore those obsolete highlights.
            if event.data_table.get_row_index(event.row_key) != event.data_table.cursor_row:
                return
            if self.selected != event.row_key.value:
                self.query_one("#confirm-import", Checkbox).value = False
            self.selected = event.row_key.value or ""
            self._review()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        event.stop()  # Import rows must never become playback paths.

    def _review(self) -> None:
        job = self.jobs.get(self.selected)
        can_accept = bool(
            job and job["state"] in ("review", "committing") and not job["manifest"]["issues"]
        )
        # The import backend also checks whether interrupted acceptance published files.
        can_discard = bool(job and job["state"] in ("review", "failed", "staging", "committing"))
        confirmed = self.query_one("#confirm-import", Checkbox)
        confirmed.disabled = self.busy or not can_accept
        self.query_one("#accept-import", Button).disabled = (
            self.busy or not can_accept or not confirmed.value
        )
        self.query_one("#accept-import", Button).label = (
            "Resume adding" if job and job["state"] == "committing" else "Add to library"
        )
        self.query_one("#discard-import", Button).disabled = self.busy or not can_discard
        files_table = self.query_one("#import-files", DataTable)
        files_table.clear()
        if not job:
            self.query_one("#import-detail", Static).update(
                "No download selected yet. Nothing has been added to your library."
            )
            return
        manifest = job["manifest"]
        for index, file in enumerate(manifest["files"]):
            track = file["track"]
            files_table.add_row(
                Text(track["title"]),
                Text(track["artist"]),
                f"{track['disc_number'] or '?'} / {track['track_number'] or '?'}",
                track["format"],
                key=str(index),
            )
        detail = (
            f"{self._state_label(job['state'])}: {Path(manifest['source']).name}\n"
            f"{len(manifest['files'])} audio files | "
            f"{manifest['duplicate_files']} duplicate files | "
            f"{len(manifest['issues'])} file problems\n"
            "Album completeness and edition have not been checked."
        )
        if manifest["issues"]:
            detail += "\nAdding is blocked. Fix the original download and review it again."
        if job["problem"] or manifest["issues"]:
            detail += "\n" + (job["problem"] or manifest["issues"][0])
        self.query_one("#import-detail", Static).update(Text(detail))

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "confirm-import":
            event.stop()
            job = self.jobs.get(self.selected)
            ready = bool(
                job and job["state"] in ("review", "committing") and not job["manifest"]["issues"]
            )
            self.query_one("#accept-import", Button).disabled = (
                self.busy or not ready or not event.value
            )

    @staticmethod
    def _state_label(state: str) -> str:
        return {
            "review": "Ready to review",
            "committing": "Adding interrupted",
            "committed": "Added to library",
            "failed": "Could not read download",
            "staging": "Reading interrupted",
            "discarded": "Cancelled",
        }.get(state, state)
