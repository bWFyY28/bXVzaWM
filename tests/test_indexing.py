import hashlib
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from helpers import write_wave

from bxvzm.database import MIGRATIONS, LibraryStore
from bxvzm.indexing import scan_library
from bxvzm.library import LibraryLayout
from bxvzm.metadata import read_track
from bxvzm.search import find_songs


class IndexingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.layout = LibraryLayout.at(self.base / "data/library", app_root=self.base)
        self.store = LibraryStore(self.layout)
        self.store.initialize()

    def test_metadata_multidisc_hash_and_quality_preserve_audio(self) -> None:
        path = write_wave(self.layout.music / "song.wav")
        before = path.read_bytes()
        report = scan_library(self.store)
        self.assertEqual((report.indexed, report.missing, report.issues), (1, 0, ()))
        track = self.store.list_tracks()[0]
        self.assertEqual((track.title, track.artist), ("Circles", "Post Malone"))
        self.assertEqual((track.disc_number, track.track_number), (2, 3))
        self.assertEqual((track.duration, track.sample_rate, track.bits_per_sample), (1, 8000, 16))
        self.assertEqual(track.relative_path, "music/song.wav")
        self.assertEqual(track.sha256, hashlib.sha256(before).hexdigest())
        self.assertEqual(path.read_bytes(), before)

    def test_rescan_updates_tags_keeps_favorite_and_missing_rows(self) -> None:
        path = write_wave(self.layout.music / "song.wav")
        scan_library(self.store)
        self.store.toggle_favorite("music/song.wav")
        write_wave(path, title="Updated title")
        scan_library(self.store)
        self.assertTrue(self.store.list_tracks()[0].favorite)
        self.assertEqual(self.store.list_tracks()[0].title, "Updated title")
        path.unlink()
        self.assertEqual(scan_library(self.store).missing, 1)
        self.assertFalse(self.store.list_tracks()[0].available)
        self.assertTrue(self.store.list_tracks()[0].favorite)
        write_wave(path)
        scan_library(self.store)
        self.assertTrue(self.store.list_tracks()[0].available)
        self.assertTrue(self.store.list_tracks()[0].favorite)

    def test_duplicates_keep_independent_paths_and_favorites(self) -> None:
        path = write_wave(self.layout.music / "first.wav")
        shutil.copyfile(path, self.layout.music / "second.wav")
        self.assertEqual(scan_library(self.store).duplicate_files, 1)
        self.store.toggle_favorite("music/first.wav")
        self.assertEqual(sum(track.favorite for track in self.store.list_tracks()), 1)

    def test_corrupt_audio_does_not_hide_valid_audio(self) -> None:
        write_wave(self.layout.music / "song.wav")
        (self.layout.music / "corrupt.flac").write_bytes(b"not audio")
        report = scan_library(self.store)
        self.assertEqual(report.indexed, 1)
        self.assertEqual(len(report.issues), 1)
        self.assertEqual(report.issues[0].path, "music/corrupt.flac")
        self.assertEqual(len(self.store.load_state("last_scan")["issues"]), 1)

    def test_untagged_audio_uses_explicit_unknowns(self) -> None:
        path = write_wave(self.layout.music / "untagged.wav")
        from mutagen.wave import WAVE

        WAVE(path).delete()
        track = read_track(path, "music/untagged.wav")
        self.assertEqual(
            (track.title, track.artist, track.album),
            ("untagged", "Unknown artist", "Unknown album"),
        )
        self.assertEqual((track.disc_number, track.track_number), (0, 0))

    def test_traversal_failure_preserves_previous_snapshot(self) -> None:
        write_wave(self.layout.music / "song.wav")
        scan_library(self.store)
        before = self.store.list_tracks()
        with patch("bxvzm.indexing.os.walk", side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                scan_library(self.store)
        self.assertEqual(self.store.list_tracks(), before)

    def test_failed_snapshot_commit_rolls_back_unavailable_flags(self) -> None:
        write_wave(self.layout.music / "song.wav")
        scan_library(self.store)
        before = self.store.list_tracks()
        with closing(sqlite3.connect(self.layout.database)) as connection, connection:
            connection.execute(
                "CREATE TRIGGER fail_scan BEFORE INSERT ON app_state "
                "WHEN NEW.key = 'last_scan' BEGIN SELECT RAISE(ABORT, 'fail'); END"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.replace_scan([], [], 0)
        self.assertEqual(self.store.list_tracks(), before)

    def test_existing_schema_one_migrates_without_losing_state(self) -> None:
        old = LibraryLayout.at(self.base / "data/old", app_root=self.base)
        old.initialize()
        with closing(sqlite3.connect(old.database)) as connection, connection:
            for statement in MIGRATIONS[0]:
                connection.execute(statement)
            connection.execute("INSERT INTO app_state VALUES ('sentinel', '42')")
            connection.execute("PRAGMA user_version = 1")
        store = LibraryStore(old)
        store.initialize()
        self.assertEqual(store.load_state("sentinel"), 42)
        self.assertEqual(store.list_tracks(), [])

    def test_relocation_preserves_tracks_hashes_and_favorites(self) -> None:
        write_wave(self.layout.music / "song.wav")
        scan_library(self.store)
        self.store.toggle_favorite("music/song.wav")
        relocated = LibraryLayout.at(self.base / "data/moved", app_root=self.base)
        shutil.copytree(self.layout.root, relocated.root)
        store = LibraryStore(relocated)
        store.initialize()
        self.assertEqual(store.list_tracks(), self.store.list_tracks())
        self.assertEqual(scan_library(store).indexed, 1)
        self.assertNotIn(str(self.layout.root).encode(), relocated.database.read_bytes())

    def test_symlink_files_and_directories_are_excluded(self) -> None:
        outside = self.base / "outside"
        write_wave(outside / "external.wav")
        try:
            (self.layout.music / "link.wav").symlink_to(outside / "external.wav")
            (self.layout.music / "folder").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Symlink creation requires Windows privilege")
        report = scan_library(self.store)
        self.assertEqual(report.indexed, 0)
        self.assertEqual(len(report.issues), 2)

    def test_fuzzy_search_handles_typo_and_artist_and_ignores_missing(self) -> None:
        write_wave(self.layout.music / "circles.wav")
        write_wave(self.layout.music / "other.wav", "Another song", "Another artist")
        scan_library(self.store)
        matches = find_songs(self.store.list_tracks(), "cirle")
        self.assertEqual(matches[0].track.title, "Circles")
        self.assertEqual(
            find_songs(self.store.list_tracks(), "post malone circles")[0].track.title, "Circles"
        )
        self.assertEqual(find_songs(self.store.list_tracks(), "!!!"), [])
        (self.layout.music / "circles.wav").unlink()
        scan_library(self.store)
        self.assertEqual(find_songs(self.store.list_tracks(), "cirle"), [])
