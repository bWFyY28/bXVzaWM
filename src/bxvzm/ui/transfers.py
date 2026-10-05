"""Text-only download and import panels; transfer I/O stays in workers."""

import os
import sqlite3
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, DataTable, Input, Static

from bxvzm.database import LibraryStore
from bxvzm.transfers.imports import accept_import, discard_import, stage_import
from bxvzm.transfers.links import DOUBLEDOUBLE_URL, open_download_page, validate_provider_url


class DownloadPanel(Vertical):
    def compose(self) -> ComposeResult:
        yield Static("Download music | Deezer / TIDAL / Amazon Music", classes="empty-state")
        yield Input(placeholder="Paste an HTTPS album or track URL", id="download-url")
        with Horizontal(classes="transfer-actions"):
            yield Button("Copy link", id="copy-provider")
            yield Button("Open DoubleDouble", id="open-download")
        yield Static(
            f"Download in your browser at {DOUBLEDOUBLE_URL}\n"
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
            message = "Paste the provider URL in DoubleDouble and finish the download manually."
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
        yield Input(placeholder="Downloaded ZIP, audio file, or folder path", id="import-path")
        with Horizontal(classes="transfer-actions"):
            yield Button("Stage files", id="stage-import")
            yield Button("Refresh jobs", id="refresh-imports")
        yield DataTable(id="import-jobs", cursor_type="row", zebra_stripes=False)
        yield Static(
            "Choose a job to review; source audio is preserved.", id="import-detail", markup=False
        )
        with Horizontal(classes="transfer-actions"):
            yield Button("Accept unverified", id="accept-import", disabled=True)
            yield Button("Discard staged", id="discard-import", disabled=True)

    def on_mount(self) -> None:
        self.query_one("#import-jobs", DataTable).add_columns("Job", "State", "Files", "Source")
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
                self.query_one("#import-detail", Static).update(
                    "Select a downloaded file or folder."
                )
                return
            self.busy = True
            for button in self.query(Button):
                button.disabled = True
            self.query_one("#import-detail", Static).update(f"{action.capitalize()} in progress...")
            url = (
                self.app.query_one("#download-url", Input).value.strip()
                if action == "stage"
                else ""
            )
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
                message = f"Accepted {count} files as unverified. Source audio preserved."
            elif action == "discard":
                discard_import(self.store, job_id)
                message = "Staged files discarded. Original source preserved."
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
        table = self.query_one("#import-jobs", DataTable)
        table.clear()
        for job in jobs:
            table.add_row(
                job["job_id"][:8],
                job["state"],
                str(len(job["manifest"]["files"])),
                Text(job["manifest"]["source"]),
                key=job["job_id"],
            )
        self.query_one("#stage-import", Button).disabled = False
        self.query_one("#refresh-imports", Button).disabled = False
        self.selected = selected if selected in self.jobs else next(iter(self.jobs), "")
        if self.selected:
            table.move_cursor(row=table.get_row_index(self.selected))
        self._review()
        if message:
            self.query_one("#import-detail", Static).update(Text(message))
        if accepted:
            self.app.action_scan()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        event.stop()
        if event.row_key.value in self.jobs:
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
        self.query_one("#accept-import", Button).disabled = self.busy or not can_accept
        self.query_one("#discard-import", Button).disabled = self.busy or not can_discard
        if not job:
            return
        manifest = job["manifest"]
        filenames = "\n".join(
            f"{index}. Disc {file['track']['disc_number'] or '?'} / "
            f"Track {file['track']['track_number'] or '?'} | "
            f"{file['track']['title']} - {file['track']['artist']} "
            f"({file['track']['format']}) | {file['source_name']}"
            for index, file in enumerate(manifest["files"], 1)
        )
        detail = (
            f"{job['job_id']} | Completeness: unknown | Edition: unknown\n"
            f"{len(manifest['files'])} files | {manifest['duplicate_files']} duplicates | "
            f"{len(manifest['issues'])} issues\n{filenames}"
        )
        if job["problem"] or manifest["issues"]:
            detail += "\n" + (job["problem"] or manifest["issues"][0])
        self.query_one("#import-detail", Static).update(Text(detail))
