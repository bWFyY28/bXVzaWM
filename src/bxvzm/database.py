"""Versioned, transactional SQLite foundation.

Each operation owns its connection, allowing callers to run I/O in workers.
Only library state belongs here; portable preferences live in config.py.
"""

import json
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from dataclasses import asdict
from typing import Any

from bxvzm.library import LibraryLayout
from bxvzm.metadata import Track

MIGRATIONS: tuple[tuple[str, ...], ...] = (
    (
        "CREATE TABLE app_state (key TEXT PRIMARY KEY, value_json TEXT NOT NULL)",
        "CREATE TABLE library_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
        "INSERT INTO library_metadata (key, value) "
        "VALUES ('created_at', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
    ),
    (
        "CREATE TABLE tracks ("
        "relative_path TEXT PRIMARY KEY, title TEXT NOT NULL, artist TEXT NOT NULL, "
        "album TEXT NOT NULL, album_artist TEXT NOT NULL, disc_number INTEGER NOT NULL, "
        "track_number INTEGER NOT NULL, duration REAL NOT NULL, format TEXT NOT NULL, "
        "sample_rate INTEGER NOT NULL, bits_per_sample INTEGER NOT NULL, bitrate INTEGER NOT NULL, "
        "sha256 TEXT NOT NULL, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, "
        "favorite INTEGER NOT NULL DEFAULT 0 CHECK (favorite IN (0, 1)), "
        "available INTEGER NOT NULL DEFAULT 1 CHECK (available IN (0, 1)))",
        "CREATE INDEX tracks_hash ON tracks (sha256)",
    ),
)
SCHEMA_VERSION = len(MIGRATIONS)


class DatabaseVersionError(RuntimeError):
    """The library was created by a newer application."""


class LibraryStore:
    def __init__(self, layout: LibraryLayout) -> None:
        self.layout = layout

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.layout.database, timeout=10)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> int:
        self.layout.initialize()
        with closing(self._connect()) as connection:
            # Re-read the version under the lock so concurrent starts cannot race.
            connection.execute("BEGIN IMMEDIATE")
            try:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version > SCHEMA_VERSION:
                    raise DatabaseVersionError(
                        f"Library schema {version} is newer than supported schema "
                        f"{SCHEMA_VERSION}. Upgrade bXVzaVM before opening it."
                    )
                for index in range(version, SCHEMA_VERSION):
                    for statement in MIGRATIONS[index]:
                        connection.execute(statement)
                    connection.execute(f"PRAGMA user_version = {index + 1}")
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return SCHEMA_VERSION

    def load_state(self, key: str, default: Any = None) -> Any:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT value_json FROM app_state WHERE key = ?", (key,)
            ).fetchone()
        return default if row is None else json.loads(row[0])

    def save_state(self, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False, allow_nan=False)
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO app_state (key, value_json) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
                (key, payload),
            )

    def list_tracks(self) -> list[Track]:
        with closing(self._connect()) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM tracks ORDER BY album_artist COLLATE NOCASE, "
                "album COLLATE NOCASE, disc_number, track_number, "
                "title COLLATE NOCASE, relative_path"
            ).fetchall()
        return [Track(**dict(row)) for row in rows]

    def toggle_favorite(self, relative_path: str) -> None:
        self.layout.resolve_relative(relative_path)
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                "UPDATE tracks SET favorite = 1 - favorite WHERE relative_path = ?",
                (relative_path,),
            )
            if not cursor.rowcount:
                raise ValueError("Track is no longer indexed")

    def replace_scan(
        self, tracks: Sequence[Track], issues: list[dict[str, str]], duplicates: int
    ) -> int:
        """Atomically refresh metadata; retain missing rows and user favorites."""
        for track in tracks:
            target = self.layout.resolve_relative(track.relative_path)
            if not target.is_relative_to(self.layout.resolve_relative("music")):
                raise ValueError("Indexed tracks must stay inside music/")
        columns = tuple(key for key in Track.__dataclass_fields__ if key != "favorite")
        # Column names come exclusively from the fixed Track declaration, never file tags.
        assignments = ", ".join(f"{column}=excluded.{column}" for column in columns[1:])
        placeholders = ", ".join("?" for _ in columns)
        with closing(self._connect()) as connection, connection:
            connection.execute("UPDATE tracks SET available = 0")
            connection.executemany(
                f"INSERT INTO tracks ({', '.join(columns)}) VALUES ({placeholders}) "
                f"ON CONFLICT(relative_path) DO UPDATE SET {assignments}",
                [tuple(asdict(track)[column] for column in columns) for track in tracks],
            )
            missing = connection.execute(
                "SELECT count(*) FROM tracks WHERE available = 0"
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO app_state (key, value_json) VALUES ('last_scan', ?) "
                "ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json",
                (json.dumps({"issues": issues, "duplicate_files": duplicates}),),
            )
        return missing
