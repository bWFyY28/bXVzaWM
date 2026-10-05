"""Bounded staging and explicitly accepted, recoverable unverified imports."""

import hashlib
import os
import re
import shutil
import sqlite3
import stat
import uuid
import zipfile
from collections import Counter
from dataclasses import asdict
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO

from mutagen import MutagenError

from bxvzm.database import LibraryStore
from bxvzm.locking import exclusive_lock
from bxvzm.metadata import SUPPORTED_SUFFIXES, Track, read_track
from bxvzm.transfers.links import validate_provider_url

MAX_ENTRIES = 10_000
MAX_BYTES = 10 * 1024**3
CHUNK_SIZE = 1024 * 1024


def _job_path(store: LibraryStore, job_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise ValueError("Use the full import job ID from --imports")
    path = store.layout.resolve_relative(f".staging/{job_id}")
    if path != store.layout.staging / job_id or store.layout.staging.is_symlink():
        raise ValueError("Import staging must not contain links")
    return path


def _archive_name(entry: zipfile.ZipInfo) -> str:
    # ZipInfo normalizes Windows separators and truncates NULs in filename.
    # Inspect the original header name before either normalization hides an escape.
    name = entry.orig_filename.rstrip("/")
    path = PurePosixPath(name)
    mode = entry.external_attr >> 16
    if (
        not name
        or path.is_absolute()
        or PureWindowsPath(name).drive
        or any(part in ("", ".", "..") for part in name.split("/"))
        or "\\" in name
        or ":" in name
        or any(ord(c) < 32 for c in name)
        or stat.S_ISLNK(mode)
        or stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)
        or entry.flag_bits & 1
    ):
        raise ValueError(f"Unsafe or encrypted ZIP entry: {name!r}")
    return name


def _copy_bounded(stream: BinaryIO, target: Path, budget: list[int], maximum: int) -> None:
    with target.open("xb") as output:
        while chunk := stream.read(CHUNK_SIZE):
            budget[0] += len(chunk)
            if budget[0] > maximum:
                raise ValueError("Import exceeds the extracted-size limit")
            output.write(chunk)


def stage_import(
    store: LibraryStore,
    source: Path,
    provider_url: str = "",
    *,
    max_entries: int = MAX_ENTRIES,
    max_bytes: int = MAX_BYTES,
) -> dict:
    with exclusive_lock(store.layout, ".imports.lock") as acquired:
        if not acquired:
            raise ValueError("Another import operation is running; retry when it finishes")
        return _stage_import(
            store, source, provider_url, max_entries=max_entries, max_bytes=max_bytes
        )


def _stage_import(
    store: LibraryStore,
    source: Path,
    provider_url: str,
    *,
    max_entries: int,
    max_bytes: int,
) -> dict:
    """Read a selected ZIP/file/folder; write only inside this library's staging.

    Archive names are validated but never used as extraction destinations. Every
    staged audio file gets an ordinal filename, avoiding Windows name collisions.
    """
    if max_entries < 1 or max_bytes < 1:
        raise ValueError("Import limits must be positive")
    source = source.expanduser().absolute()
    if source.is_symlink() or source.is_junction() or not source.exists():
        raise ValueError("Select an existing file or folder without links")
    source = source.resolve()
    if source.is_dir() and (
        source == store.layout.root
        or source in store.layout.root.parents
        or source.is_relative_to(store.layout.staging)
    ):
        raise ValueError("Do not import the bundle, library root, or staging folder")
    url = validate_provider_url(provider_url).url if provider_url.strip() else ""
    job_id = uuid.uuid4().hex
    root = _job_path(store, job_id)
    manifest = {
        "source": source.name,
        "provider_url": url,
        "files": [],
        "issues": [],
        "completeness": "unknown",
        "edition_confidence": "unknown",
        "accepted_unverified": False,
        "duplicate_files": 0,
        "destination": f"music/Imported [unverified-{job_id}]",
    }
    store.create_import(job_id, manifest)
    budget = [0]
    count = 0
    try:
        root.mkdir(parents=True, exist_ok=False)
        files_root = root / "files"
        files_root.mkdir()

        def stage(stream, name: str) -> None:
            nonlocal count
            count += 1
            if count > max_entries:
                raise ValueError("Import exceeds the entry-count limit")
            target = files_root / f"{count:05}{Path(name).suffix.lower()}"
            _copy_bounded(stream, target, budget, max_bytes)
            relative = store.layout.relative_path(target)
            try:
                track = read_track(target, relative, fallback_title=Path(name).stem)
            except (OSError, ValueError, MutagenError) as error:
                manifest["issues"].append(f"{name}: {error}")
                return
            manifest["files"].append({"source_name": name, "track": asdict(track)})

        if source.is_file() and source.suffix.lower() == ".zip":
            with zipfile.ZipFile(source) as package:
                entries = package.infolist()
                if len(entries) > max_entries or sum(e.file_size for e in entries) > max_bytes:
                    raise ValueError("ZIP exceeds the entry-count or extracted-size limit")
                seen = set()
                for entry in entries:
                    name = _archive_name(entry)
                    if name.casefold() in seen:
                        raise ValueError(f"Duplicate ZIP entry: {name}")
                    seen.add(name.casefold())
                for entry in entries:
                    if (
                        not entry.is_dir()
                        and Path(entry.filename).suffix.lower() in SUPPORTED_SUFFIXES
                    ):
                        with package.open(entry) as stream:
                            stage(stream, entry.filename)
        else:
            candidates = []
            if source.is_dir():

                def failed_walk(error: OSError) -> None:
                    raise error

                entries_seen = 0
                for directory, folders, filenames in os.walk(
                    source, followlinks=False, onerror=failed_walk
                ):
                    entries_seen += len(folders) + len(filenames)
                    if entries_seen > max_entries:
                        raise ValueError("Folder exceeds the entry-count limit")
                    for name in folders + filenames:
                        child = Path(directory) / name
                        if child.is_symlink() or child.is_junction():
                            raise ValueError("Import folders must not contain links")
                    candidates.extend(
                        Path(directory) / name
                        for name in filenames
                        if Path(name).suffix.lower() in SUPPORTED_SUFFIXES
                    )
            elif source.is_file() and source.suffix.lower() in SUPPORTED_SUFFIXES:
                candidates = [source]
            else:
                raise ValueError("Select a ZIP, supported audio file, or audio folder")
            for path in sorted(candidates):
                before = path.stat()
                if not stat.S_ISREG(before.st_mode) or before.st_size + budget[0] > max_bytes:
                    raise ValueError("Invalid file or import exceeds the extracted-size limit")
                name = path.relative_to(source).as_posix() if source.is_dir() else path.name
                with path.open("rb") as stream:
                    stage(stream, name)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError("Source changed during staging; retry after copying finishes")
        if not manifest["files"]:
            raise ValueError("No readable supported audio files were found")
        counts = Counter(file["track"]["sha256"] for file in manifest["files"])
        manifest["duplicate_files"] = sum(number - 1 for number in counts.values())
        store.update_import(job_id, "review", manifest)
    except Exception as error:
        store.update_import(job_id, "failed", manifest, str(error))
        raise ValueError(f"Import {job_id} failed: {error}") from error
    return store.get_import(job_id)


def _safe_name(value: str, maximum: int = 40) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")[:maximum].rstrip(" .")
    if not value:
        value = "Unknown"
    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", value.split(".")[0], re.I):
        value = "_" + value
    return value


def accept_import(store: LibraryStore, job_id: str, *, accept_unverified: bool = False) -> int:
    with exclusive_lock(store.layout, ".imports.lock") as acquired:
        if not acquired:
            raise ValueError("Another import operation is running; retry when it finishes")
        return _accept_import(store, job_id, accept_unverified=accept_unverified)


def _accept_import(store: LibraryStore, job_id: str, *, accept_unverified: bool) -> int:
    root = _job_path(store, job_id)
    job = store.get_import(job_id)
    manifest = job["manifest"]
    if not accept_unverified:
        raise ValueError(
            "Completeness and edition are unknown; explicitly accept this as unverified"
        )
    if job["state"] not in ("review", "committing", "committed"):
        raise ValueError("Only a reviewed or interrupted acceptance can be accepted")
    if job["state"] == "review":
        if manifest["issues"]:
            raise ValueError(
                "Unreadable files remain; discard and retry with repaired source files"
            )
        manifest["accepted_unverified"] = True
        for index, file in enumerate(manifest["files"], 1):
            track = Track(**file["track"])
            name = f"{index:05} - {_safe_name(track.title, 48)}-{track.sha256[:8]}"
            name += Path(track.relative_path).suffix
            file["destination"] = "/".join(
                (
                    manifest["destination"],
                    _safe_name(track.album_artist),
                    _safe_name(track.album),
                    name,
                )
            )
        if not store.update_import(job_id, "committing", manifest, expected_state="review"):
            return _accept_import(store, job_id, accept_unverified=True)

    def prepare() -> list[Track]:
        destination = store.layout.resolve_relative(manifest["destination"])
        if destination != store.layout.music / f"Imported [unverified-{job_id}]":
            raise ValueError("Invalid import destination")
        prepared = store.layout.resolve_relative(f".staging/{job_id}/prepared")
        if prepared != root / "prepared":
            raise ValueError("Prepared directory must not contain links")
        if not destination.exists():
            prepared.mkdir(exist_ok=True)
            for file in manifest["files"]:
                track = Track(**file["track"])
                source = store.layout.resolve_relative(track.relative_path)
                if not source.is_relative_to(root / "files"):
                    raise ValueError("Staged source escapes its import job")
                target = prepared / Path(file["destination"]).relative_to(manifest["destination"])
                if target.resolve() != target or not target.is_relative_to(prepared):
                    raise ValueError("Prepared audio escapes its import job")
                target.parent.mkdir(parents=True, exist_ok=True)
                # An interrupted copy can leave a partial file in our owned prepared tree.
                # Check the staged original before replacing that partial copy.
                with source.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != track.sha256:
                        raise ValueError(
                            "Staged audio changed; restore it from the original or stage a new job"
                        )
                if target.exists():
                    with target.open("rb") as stream:
                        intact = hashlib.file_digest(stream, "sha256").hexdigest() == track.sha256
                    if not intact:
                        target.unlink()
                if not target.exists():
                    with source.open("rb") as stream:
                        _copy_bounded(stream, target, [0], MAX_BYTES)
                with target.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != track.sha256:
                        raise ValueError("Staged audio changed; keep the job for repair")
            prepared.rename(destination)
        tracks = []
        for file in manifest["files"]:
            path = store.layout.resolve_relative(file["destination"])
            if path != store.layout.root / file["destination"] or not path.is_relative_to(
                destination
            ):
                raise ValueError("Accepted audio escapes its import directory")
            track = read_track(
                path, file["destination"], fallback_title=Path(file["source_name"]).stem
            )
            if track.sha256 != file["track"]["sha256"]:
                raise ValueError("Accepted audio changed; keep the job for repair")
            tracks.append(track)
        return tracks

    try:
        tracks = prepare() if job["state"] != "committed" else []
        count = store.commit_import(job_id, tracks)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as error:
        store.update_import(job_id, "committing", manifest, str(error), expected_state="committing")
        raise
    if root.exists():
        # This exact allocated job directory was checked above; user sources are never removed.
        shutil.rmtree(root)
    return count


def discard_import(store: LibraryStore, job_id: str) -> None:
    with exclusive_lock(store.layout, ".imports.lock") as acquired:
        if not acquired:
            raise ValueError("Another import operation is running; retry when it finishes")
        _discard_import(store, job_id)


def _discard_import(store: LibraryStore, job_id: str) -> None:
    root = _job_path(store, job_id)
    job = store.get_import(job_id)
    unpublished = (
        job["state"] == "committing"
        and not store.layout.resolve_relative(job["manifest"]["destination"]).exists()
    )
    if job["state"] not in ("review", "failed", "staging", "discarded") and not unpublished:
        raise ValueError(
            "Committed/interrupted acceptance files are preserved; resume acceptance first"
        )
    if root.exists():
        shutil.rmtree(root)
    store.update_import(job_id, "discarded", job["manifest"])
