"""First-milestone shell; storage initialization happens before the UI starts."""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import Footer, Header, Static, TabbedContent, TabPane

from bxvzm.library import LibraryLayout


class HelpScreen(ModalScreen[None]):
    BINDINGS = [("escape", "dismiss", "Close"), ("question_mark", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        yield Static(
            "bXVzaVM\n\n"
            "1–5  Switch views\n"
            "Tab / Shift+Tab  Move focus\n"
            "Arrow keys  Navigate tabs\n"
            "?  Help    q  Quit\n\n"
            "Esc  Close this help",
            id="help-dialog",
        )


class MusicApp(App[None]):
    TITLE = "bXVzaVM"
    SUB_TITLE = "Local music"
    CSS_PATH = "themes/gruvbox.tcss"
    BINDINGS = [
        Binding("1", "view('library')", "Library", show=False),
        Binding("2", "view('search')", "Search", show=False),
        Binding("3", "view('favorites')", "Favorites", show=False),
        Binding("4", "view('playlists')", "Playlists", show=False),
        Binding("5", "view('imports')", "Imports", show=False),
        Binding("question_mark", "help", "Help"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, layout: LibraryLayout) -> None:
        super().__init__()
        self.layout = layout
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
        yield Header()
        with TabbedContent(initial="library", id="views"):
            with TabPane("Library", id="library"):
                yield Static(
                    "Your library is ready.\n\n"
                    "Local file indexing and playback are the next milestone.",
                    classes="empty-state",
                )
                yield Static(str(self.layout.root), id="library-root", markup=False)
            with TabPane("Search", id="search"):
                yield Static("Catalog search arrives in milestone 3.", classes="empty-state")
            with TabPane("Favorites", id="favorites"):
                yield Static("Favorites arrive with the local library.", classes="empty-state")
            with TabPane("Playlists", id="playlists"):
                yield Static("Playlists arrive with the local library.", classes="empty-state")
            with TabPane("Imports", id="imports"):
                yield Static("Verified imports arrive in milestone 4.", classes="empty-state")
        yield Static("No track loaded · Playback arrives in milestone 2.", id="player")
        yield Footer()

    def action_view(self, view: str) -> None:
        self.query_one("#views", TabbedContent).active = view

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

