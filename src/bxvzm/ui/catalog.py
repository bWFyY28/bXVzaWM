"""Song-name discovery; selecting a result fills the download link."""

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, DataTable, Input, Static

from bxvzm.catalog.deezer import CatalogError, CatalogSong, search_songs
from bxvzm.ui.transfers import DownloadPanel


class CatalogPanel(VerticalScroll):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[CatalogSong] = []
        self.selected: int | None = None
        self.busy = False

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="Song name and artist, e.g. Circles Post Malone", id="catalog-query"
        )
        with Horizontal(classes="transfer-actions"):
            yield Button("Search songs", id="search-catalog")
        yield Static(
            "Search the Deezer catalog; choose a result to get its album link.",
            id="catalog-status",
            markup=False,
        )
        yield DataTable(id="catalog-results", cursor_type="row", zebra_stripes=False)
        with Horizontal(classes="transfer-actions"):
            yield Button("Use album link", id="use-album", disabled=True)
            yield Button("Use track link", id="use-track", disabled=True)
        yield DownloadPanel()

    def on_mount(self) -> None:
        self.query_one("#catalog-results", DataTable).add_columns(
            "Title", "Artist", "Album", "Explicit (track)"
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "catalog-query":
            event.stop()
            self._begin_search()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "search-catalog":
            event.stop()
            self._begin_search()
        elif event.button.id in ("use-album", "use-track"):
            event.stop()
            self._choose(event.button.id == "use-album")

    def _begin_search(self) -> None:
        if self.busy:
            return
        query = self.query_one("#catalog-query", Input).value
        self.busy = True
        self.selected = None
        self.query_one("#search-catalog", Button).disabled = True
        self.query_one("#use-album", Button).disabled = True
        self.query_one("#use-track", Button).disabled = True
        self.query_one("#catalog-results", DataTable).clear()
        self.query_one("#download-url", Input).value = ""
        self.query_one("#catalog-status", Static).update("Searching Deezer...")
        self._search(query)

    @work(thread=True)
    def _search(self, query: str) -> None:
        try:
            results = search_songs(query)
            message = f"{len(results)} results from Deezer. Enter on a row uses its album link."
            if not results:
                message = "No catalog results. Try the song's full title and artist."
        except CatalogError as error:
            results, message = [], str(error)
        self.app.call_from_thread(self._loaded, results, message)

    def _loaded(self, results: list[CatalogSong], message: str) -> None:
        self.results = results
        self.busy = False
        self.query_one("#search-catalog", Button).disabled = False
        table = self.query_one("#catalog-results", DataTable)
        for index, song in enumerate(results):
            explicit = "unknown" if song.explicit is None else "yes" if song.explicit else "no"
            table.add_row(
                Text(song.title), Text(song.artist), Text(song.album), explicit, key=str(index)
            )
        self.query_one("#catalog-status", Static).update(Text(message))
        if results:
            self.selected = 0
            self.query_one("#use-album", Button).disabled = False
            self.query_one("#use-track", Button).disabled = False
            table.focus()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "catalog-results":
            event.stop()
            if event.row_key.value is not None:
                self.selected = int(event.row_key.value)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "catalog-results":
            event.stop()
            if event.row_key.value is not None:
                self.selected = int(event.row_key.value)
                self._choose(album=True)

    def _choose(self, album: bool) -> None:
        if self.busy or self.selected is None:
            return
        song = self.results[self.selected]
        link = song.album_url if album else song.track_url
        kind = "album" if album else "track"
        title = song.album if album else song.title
        self.query_one("#download-url", Input).value = link
        self.query_one("#download-status", Static).update(
            Text(
                f"Selected {song.provider} {kind}: {title}\n"
                "Open DoubleDouble to fill its URL input. "
                "Complete CAPTCHA/download in the browser.\n"
                "Catalog metadata does not verify imported files or album edition."
            )
        )
        self.query_one("#open-download", Button).focus()
