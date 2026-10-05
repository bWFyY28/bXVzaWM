"""Versioned, transactional SQLite foundation.

Each operation owns its connection, allowing callers to run I/O in workers.
Only portable state belongs here; machine preferences live in config.py.
"""

import json
import sqlite3
from contextlib import closing
from typing import Any

from bxvzm.library import LibraryLayout

MIGRATIONS: tuple[tuple[str, ...], ...] = (
    (
        "CREATE TABLE app_state (key TEXT PRIMARY KEY, value_json TEXT NOT NULL)",
        "CREATE TABLE library_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
        "INSERT INTO library_metadata (key, value) "
        "VALUES ('created_at', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))",
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

