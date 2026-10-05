import shutil
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from bxvzm.database import SCHEMA_VERSION, DatabaseVersionError, LibraryStore
from bxvzm.library import LibraryLayout


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.layout = LibraryLayout.at(self.base / "original")
        self.store = LibraryStore(self.layout)

    def test_initialize_is_repeatable_and_preserves_state(self) -> None:
        self.assertEqual(self.store.initialize(), SCHEMA_VERSION)
        self.store.save_state("queue", {"tracks": [], "position": 12, "playing": False})
        self.store.initialize()
        reopened = LibraryStore(self.layout)
        self.assertEqual(reopened.load_state("queue")["position"], 12)
        self.assertIsNone(reopened.load_state("missing"))
        self.assertEqual(reopened.load_state("missing", []), [])
        for directory in (self.layout.music, self.layout.playlists, self.layout.staging):
            self.assertTrue(directory.is_dir())

    def test_json_state_handles_unicode_and_updates(self) -> None:
        self.store.initialize()
        self.store.save_state("queue", {"title": "Âm nhạc"})
        self.assertEqual(self.store.load_state("queue"), {"title": "Âm nhạc"})
        self.store.save_state("queue", {"title": "Updated"})
        self.assertEqual(self.store.load_state("queue"), {"title": "Updated"})

    def test_newer_schema_is_refused_without_modification(self) -> None:
        self.store.initialize()
        self.store.save_state("sentinel", "preserve me")
        with closing(sqlite3.connect(self.layout.database)) as connection:
            connection.execute("PRAGMA user_version = 999")
            connection.commit()
        before = self.layout.database.read_bytes()
        with self.assertRaises(DatabaseVersionError):
            self.store.initialize()
        self.assertEqual(self.layout.database.read_bytes(), before)

    def test_failed_migration_rolls_back_ddl_and_version(self) -> None:
        migrations = (("CREATE TABLE partial (id INTEGER)", "INVALID SQL"),)
        with patch("bxvzm.database.MIGRATIONS", migrations):
            with self.assertRaises(sqlite3.Error):
                self.store.initialize()
        with closing(sqlite3.connect(self.layout.database)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 0)
            self.assertEqual(
                connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(),
                [],
            )
        self.assertEqual(self.store.initialize(), SCHEMA_VERSION)

    def test_concurrent_initialization_does_not_repeat_migrations(self) -> None:
        with ThreadPoolExecutor(max_workers=4) as workers:
            versions = list(workers.map(lambda _: self.store.initialize(), range(4)))
        self.assertEqual(versions, [SCHEMA_VERSION] * 4)

    def test_library_copy_retains_state_and_relative_paths(self) -> None:
        self.store.initialize()
        # A text fixture stands in for audio; user media is never written into the repo.
        asset = self.layout.music / "artist" / "album" / "track.fixture"
        asset.parent.mkdir(parents=True)
        asset.write_bytes(b"source bytes")
        relative = self.layout.relative_path(asset)
        self.store.save_state("queue", [relative])
        relocated = LibraryLayout.at(self.base / "relocated")
        shutil.copytree(self.layout.root, relocated.root)
        reopened = LibraryStore(relocated)
        reopened.initialize()
        self.assertEqual(reopened.load_state("queue"), [relative])
        self.assertEqual(relocated.resolve_relative(relative).read_bytes(), b"source bytes")
        self.assertNotIn(str(self.layout.root).encode(), relocated.database.read_bytes())

