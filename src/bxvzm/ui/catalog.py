"""Amazon browser discovery and explicit copied-link handoff."""

import os

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Input, Static

from bxvzm.catalog.amazon import open_search
from bxvzm.transfers.clipboard import copied_amazon_link
from bxvzm.ui.transfers import DownloadPanel


class CatalogPanel(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Static("Find music on Amazon", classes="view-heading")
        yield Input(
            placeholder="Song name and artist, e.g. Circles Post Malone", id="catalog-query"
        )
        with Horizontal(classes="transfer-actions"):
            yield Button("Search Amazon", id="search-catalog")
        yield Static(
            "Search opens Amazon Music in your browser.\n"
            "Choose an album, then use Share / Copy link.\n"
            "Use copied link below, then open DoubleDouble with its URL filled in.",
            id="catalog-status",
            markup=False,
        )
        with Horizontal(classes="transfer-actions"):
            yield Button("Use copied link", id="use-copied-amazon", disabled=os.name != "nt")
        yield DownloadPanel()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "catalog-query":
            event.stop()
            self._search(self.query_one("#catalog-query", Input).value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "search-catalog":
            event.stop()
            self._search(self.query_one("#catalog-query", Input).value)
        elif event.button.id == "use-copied-amazon":
            event.stop()
            self._read_link()

    @work(thread=True, exclusive=True)
    def _search(self, query: str) -> None:
        try:
            open_search(query)
            message = "Amazon Music opened. Choose the album and copy its Share link."
        except (OSError, ValueError, RuntimeError) as error:
            message = str(error)
        self.app.call_from_thread(self._status, message)

    @work(thread=True, exclusive=True)
    def _read_link(self) -> None:
        try:
            link = copied_amazon_link()
        except (OSError, ValueError, RuntimeError) as error:
            self.app.call_from_thread(self._status, str(error))
            return
        self.app.call_from_thread(self._selected, link.url)

    def _selected(self, url: str) -> None:
        self.query_one("#download-url", Input).value = url
        self._status("Amazon Music link selected. Open DoubleDouble to fill its URL input.")
        self.query_one("#open-download", Button).focus()

    def _status(self, message: str) -> None:
        self.query_one("#catalog-status", Static).update(Text(message))
