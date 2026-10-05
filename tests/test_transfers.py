import io
import json
import shutil
import sqlite3
import stat
import tempfile
import unittest
import zipfile
from contextlib import closing, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from helpers import write_wave

from bxvzm.cli import main
from bxvzm.database import LibraryStore
from bxvzm.indexing import scan_library
from bxvzm.library import LibraryLayout
from bxvzm.locking import exclusive_lock
from bxvzm.transfers.imports import accept_import, discard_import, stage_import
from bxvzm.transfers.links import DOUBLEDOUBLE_URL, open_download_page, validate_provider_url


class ProviderTests(unittest.TestCase):
    def test_provider_evidence_and_fixed_browser_destination(self) -> None:
        cases = (
            (
                "https://www.deezer.com/en/album/123?utm_source=x#top",
                "Deezer",
                "album",
                "https://www.deezer.com/en/album/123",
            ),
            (
                "https://listen.tidal.com/track/456",
                "TIDAL",
                "track",
                "https://listen.tidal.com/track/456",
            ),
            (
                "https://music.amazon.com/albums/B123?trackAsin=B456&ref=x",
                "Amazon Music",
                "album",
                "https://music.amazon.com/albums/B123?trackAsin=B456",
            ),
        )
        for value, provider, kind, canonical in cases:
            with self.subTest(value=value):
                link = validate_provider_url(value)
                self.assertEqual((link.provider, link.kind, link.url), (provider, kind, canonical))
                with patch("bxvzm.transfers.links.webbrowser.open", return_value=True) as browser:
                    open_download_page(link)
                browser.assert_called_once_with(DOUBLEDOUBLE_URL, new=2)

    def test_spoofed_private_and_malformed_links_are_rejected(self) -> None:
        for value in (
            "http://deezer.com/album/1",
            "https://deezer.com.evil.test/album/1",
            "https://evil.test@deezer.com/album/1",
            "https://deezer.com:8080/album/1",
            "https://localhost/album/1",
            "file:///album/1",
            "javascript:alert(1)",
            "https://deezer.com/album/../1",
            "https://deezer.com/album/%31",
            "https://deezer.com\\evil/album/1",
            "https://deezer.com/album/1\n/2",
            "https://music.amazon.com/albums/B1?trackAsin=../bad",
            "https://music.amazon.com/albums/B1?trackAsin=B2&trackAsin=B3",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_provider_url(value)


class ImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.bundle = self.base / "bundle"
        self.layout = LibraryLayout.at(self.bundle / "data/library", self.bundle)
        self.store = LibraryStore(self.layout)
        self.store.initialize()
        self.source = write_wave(self.base / "downloads/song.wav")
        self.original = self.source.read_bytes()

    def stage(self) -> dict:
        return stage_import(self.store, self.source, "https://deezer.com/track/123")

    def accept(self, job: dict) -> int:
        return accept_import(self.store, job["job_id"], accept_unverified=True)

    def test_review_explicit_acceptance_source_integrity_and_idempotence(self) -> None:
        job = self.stage()
        self.assertEqual(job["state"], "review")
        self.assertEqual(job["manifest"]["completeness"], "unknown")
        self.assertEqual(job["manifest"]["edition_confidence"], "unknown")
        self.assertEqual(job["manifest"]["files"][0]["track"]["disc_number"], 2)
        self.assertEqual(scan_library(self.store).indexed, 0)
        with self.assertRaisesRegex(ValueError, "explicitly accept"):
            accept_import(self.store, job["job_id"])
        self.assertEqual(self.accept(job), 1)
        self.assertEqual(self.accept(job), 1)
        tracks = self.store.list_tracks()
        self.assertEqual(len(tracks), 1)
        self.assertEqual(tracks[0].title, "Circles")
        self.assertIn("unverified", tracks[0].relative_path)
        self.assertEqual(
            self.layout.resolve_relative(tracks[0].relative_path).read_bytes(), self.original
        )
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertFalse((self.layout.staging / job["job_id"]).exists())
        self.assertTrue(self.store.get_import(job["job_id"])["manifest"]["accepted_unverified"])
        self.assertNotIn(str(self.base), json.dumps(self.store.get_import(job["job_id"])))

    def test_zip_multidisc_and_duplicate_bytes_remain_separate(self) -> None:
        archive = self.base / "download.zip"
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr("Disc 1/song.wav", self.original)
            package.writestr("Disc 2/song.wav", self.original)
            package.writestr("cover.jpg", b"cover")
        original_zip = archive.read_bytes()
        job = stage_import(self.store, archive)
        self.assertEqual(job["manifest"]["duplicate_files"], 1)
        self.assertEqual(self.accept(job), 2)
        other = self.stage()
        self.accept(other)
        self.assertEqual(len(self.store.list_tracks()), 3)
        self.assertEqual(archive.read_bytes(), original_zip)

    def test_untagged_import_keeps_original_filename_title_after_rescan(self) -> None:
        from mutagen.wave import WAVE

        from bxvzm.search import find_songs

        source = write_wave(self.source.parent / "Circles.wav")
        WAVE(source).delete()
        original = source.read_bytes()
        job = stage_import(self.store, source)
        self.assertEqual(job["manifest"]["files"][0]["track"]["title"], "Circles")
        self.accept(job)
        self.assertEqual(self.store.list_tracks()[0].title, "Circles")
        scan_library(self.store)
        track = self.store.list_tracks()[0]
        self.assertEqual(track.title, "Circles")
        self.assertEqual(track.artist, "Unknown artist")
        self.assertEqual(find_songs([track], "circle")[0].track, track)
        self.assertEqual(source.read_bytes(), original)

    def test_unsafe_zip_entries_including_non_audio_are_rejected(self) -> None:
        for name in (
            "../escape.txt",
            "/outside.wav",
            "C:/outside.wav",
            "folder\\song.wav",
            "a/./song.wav",
        ):
            with self.subTest(name=name):
                archive = self.base / "unsafe.zip"
                with zipfile.ZipFile(archive, "w") as package:
                    package.writestr("safe.wav", self.original)
                    entry = zipfile.ZipInfo(name)
                    entry.filename = name  # Preserve backslashes even on Windows.
                    package.writestr(entry, b"bad")
                with self.assertRaisesRegex(ValueError, "Unsafe"):
                    stage_import(self.store, archive)
        self.assertFalse((self.base / "escape.txt").exists())
        self.assertEqual(self.store.list_tracks(), [])

    def test_zip_links_collisions_and_limits(self) -> None:
        archive = self.base / "unsafe.zip"
        link = zipfile.ZipInfo("link.wav")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr(link, "../song.wav")
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            stage_import(self.store, archive)
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr("Song.wav", self.original)
            package.writestr("song.wav", self.original)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            stage_import(self.store, archive)
        with self.assertRaisesRegex(ValueError, "limit"):
            stage_import(self.store, archive, max_entries=1)
        with self.assertRaisesRegex(ValueError, "limit"):
            stage_import(self.store, archive, max_bytes=100)
        with self.assertRaisesRegex(ValueError, "limit"):
            stage_import(self.store, self.source, max_bytes=100)

    def test_corrupt_files_block_acceptance_and_discard_preserves_originals(self) -> None:
        broken = self.source.parent / "broken.mp3"
        broken.write_bytes(b"not audio")
        job = stage_import(self.store, self.source.parent)
        self.assertEqual(len(job["manifest"]["issues"]), 1)
        with self.assertRaisesRegex(ValueError, "Unreadable"):
            self.accept(job)
        discard_import(self.store, job["job_id"])
        self.assertEqual(self.store.get_import(job["job_id"])["state"], "discarded")
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertTrue(broken.exists())
        with self.assertRaises(ValueError):
            discard_import(self.store, "../downloads")
        with self.assertRaises(ValueError):
            stage_import(self.store, self.bundle)

    def test_failed_empty_import_stays_inspectable(self) -> None:
        broken = self.source.parent / "broken.mp3"
        broken.write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "No readable"):
            stage_import(self.store, broken)
        job = self.store.list_imports()[0]
        self.assertEqual(job["state"], "failed")
        self.assertTrue(job["problem"])
        discard_import(self.store, job["job_id"])

    def test_partial_prepared_copy_resumes(self) -> None:
        job = self.stage()
        with patch("bxvzm.transfers.imports._copy_bounded") as copy:

            def interrupted(stream, target, budget, maximum):
                target.write_bytes(b"partial")
                raise OSError("interrupted copy")

            copy.side_effect = interrupted
            with self.assertRaisesRegex(OSError, "interrupted"):
                self.accept(job)
        self.assertEqual(self.store.get_import(job["job_id"])["state"], "committing")
        self.assertEqual(self.store.list_tracks(), [])
        self.assertEqual(self.accept(job), 1)
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_database_rollback_after_move_recovers_and_scan_holds_pending_files(self) -> None:
        job = self.stage()
        with closing(sqlite3.connect(self.layout.database)) as connection, connection:
            connection.execute(
                "CREATE TRIGGER fail_commit BEFORE UPDATE OF state ON import_jobs "
                "WHEN NEW.state='committed' BEGIN SELECT RAISE(ABORT, 'interrupted'); END"
            )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "interrupted"):
            self.accept(job)
        self.assertTrue(self.layout.resolve_relative(job["manifest"]["destination"]).is_dir())
        self.assertEqual(self.store.list_tracks(), [])
        self.assertEqual(scan_library(self.store).indexed, 0)
        with closing(sqlite3.connect(self.layout.database)) as connection, connection:
            connection.execute("DROP TRIGGER fail_commit")
        self.assertEqual(self.accept(job), 1)
        self.assertEqual(self.accept(job), 1)

    def test_scan_snapshot_does_not_hide_new_import_and_state_compare_preserves_commit(
        self,
    ) -> None:
        baseline = [track.relative_path for track in self.store.list_tracks()]
        job = self.stage()
        self.accept(job)
        self.store.replace_scan([], [], 0, baseline)
        self.assertTrue(self.store.list_tracks()[0].available)
        self.assertFalse(
            self.store.update_import(
                job["job_id"], "committing", job["manifest"], expected_state="review"
            )
        )
        self.assertEqual(self.store.get_import(job["job_id"])["state"], "committed")

    def test_staged_jobs_survive_bundle_relocation(self) -> None:
        job = self.stage()
        moved = self.base / "moved"
        shutil.move(self.bundle, moved)
        store = LibraryStore(LibraryLayout.at(moved / "data/library", moved))
        store.initialize()
        self.assertEqual(accept_import(store, job["job_id"], accept_unverified=True), 1)
        self.assertTrue(
            store.layout.resolve_relative(store.list_tracks()[0].relative_path).exists()
        )

    def test_tampered_staging_is_not_accepted(self) -> None:
        job = self.stage()
        self.layout.resolve_relative(
            job["manifest"]["files"][0]["track"]["relative_path"]
        ).write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "Staged audio changed"):
            self.accept(job)
        self.assertEqual(self.store.list_tracks(), [])
        discard_import(self.store, job["job_id"])
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_copy_does_not_block_playback_database_writes(self) -> None:
        from bxvzm.transfers.imports import _copy_bounded

        job = self.stage()

        def copy(stream, target, budget, maximum):
            self.store.save_state("playback", {"position": 42})
            _copy_bounded(stream, target, budget, maximum)

        with patch("bxvzm.transfers.imports._copy_bounded", side_effect=copy):
            self.assertEqual(self.accept(job), 1)
        self.assertEqual(self.store.load_state("playback")["position"], 42)

    def test_import_lock_blocks_concurrent_mutation_and_releases(self) -> None:
        job = self.stage()
        with exclusive_lock(self.layout, ".imports.lock") as acquired:
            self.assertTrue(acquired)
            with self.assertRaisesRegex(ValueError, "Another import"):
                self.accept(job)
            with self.assertRaisesRegex(ValueError, "Another import"):
                discard_import(self.store, job["job_id"])
            with self.assertRaisesRegex(ValueError, "Another import"):
                self.stage()
        self.assertEqual(self.accept(job), 1)

    def test_staging_and_prepared_links_cannot_redirect_writes_or_deletion(self) -> None:
        job = self.stage()
        outside = self.base / "outside"
        outside.mkdir()
        marker = outside / "keep.txt"
        marker.write_text("keep")
        prepared = self.layout.staging / job["job_id"] / "prepared"
        try:
            prepared.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Windows account cannot create symlinks")
        with self.assertRaises(ValueError):
            self.accept(job)
        self.assertEqual(marker.read_text(), "keep")
        self.assertEqual(list(outside.iterdir()), [marker])

    def test_cli_handoff_import_review_and_accept(self) -> None:
        with patch("bxvzm.config.application_root", return_value=self.bundle):
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["--download", "https://deezer.com/track/123"]), 0)
                self.assertIn("download manually", output.getvalue())
                self.assertEqual(main(["--import", str(self.source)]), 0)
            job = self.store.list_imports()[0]
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["--review-import", job["job_id"]]), 0)
                self.assertIn('"completeness": "unknown"', output.getvalue())
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(["--accept-import", job["job_id"]]), 1)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--accept-import", job["job_id"], "--accept-unverified"]), 0)

    def test_open_tui_alias(self) -> None:
        with (
            patch("bxvzm.config.application_root", return_value=self.bundle),
            patch("bxvzm.ui.MusicApp") as app,
        ):
            self.assertEqual(main(["open", "tui"]), 0)
        app.return_value.run.assert_called_once()
