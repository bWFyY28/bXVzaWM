"""Portable library layout and strict relative-path handling."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from bxvzm.config import validate_library_root


@dataclass(frozen=True)
class LibraryLayout:
    root: Path

    @classmethod
    def at(cls, root: Path, app_root: Path | None = None) -> "LibraryLayout":
        return cls(validate_library_root(root, app_root))

    @property
    def database(self) -> Path:
        return self.root / "library.sqlite3"

    @property
    def music(self) -> Path:
        return self.root / "music"

    @property
    def playlists(self) -> Path:
        return self.root / "playlists"

    @property
    def staging(self) -> Path:
        return self.root / ".staging"

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        # Check all locations before creating any of them, including SQLite sidecars.
        for name in (
            "music",
            "playlists",
            ".staging",
            "library.sqlite3",
            "library.sqlite3-journal",
            "library.sqlite3-wal",
            "library.sqlite3-shm",
        ):
            self.resolve_relative(name)
        for directory in (self.music, self.playlists, self.staging):
            directory.mkdir(exist_ok=True)

    def resolve_relative(self, relative: str) -> Path:
        """Reject absolute, traversal, Windows drive, and symlink escapes."""
        portable = PurePosixPath(relative)
        windows = PureWindowsPath(relative)
        if (
            not relative
            or "\\" in relative
            or ":" in relative
            or "\x00" in relative
            or portable.is_absolute()
            or windows.drive
            or ".." in portable.parts
            or portable == PurePosixPath(".")
        ):
            raise ValueError(f"Invalid library-relative path: {relative!r}")
        target = (self.root / portable).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError(f"Path escapes the library: {relative!r}")
        return target

    def relative_path(self, path: Path) -> str:
        """Serialize paths with forward slashes for relocation across OSes."""
        relative = path.resolve().relative_to(self.root).as_posix()
        self.resolve_relative(relative)
        return relative
