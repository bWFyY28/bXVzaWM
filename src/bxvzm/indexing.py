"""Read-only music scans; only a completed traversal updates the index."""

import os
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import mutagen

from bxvzm.database import LibraryStore
from bxvzm.metadata import SUPPORTED_SUFFIXES, read_track


@dataclass(frozen=True)
class ScanIssue:
    path: str
    reason: str


@dataclass(frozen=True)
class ScanReport:
    indexed: int
    missing: int
    duplicate_files: int
    issues: tuple[ScanIssue, ...]


def scan_library(store: LibraryStore) -> ScanReport:
    """Index files already in music/, preserving duplicates and favorite identities.

    Symlinks and Windows junctions are excluded. Traversal failure leaves the
    previous snapshot intact; corrupt individual files are reported as unavailable.
    This is local indexing, not an import or edition-verification decision.
    """
    layout = store.layout
    music = layout.resolve_relative("music")
    if layout.music.is_symlink() or layout.music.is_junction():
        raise ValueError("The music directory must not be a symbolic link or junction")
    if not music.is_dir():
        raise ValueError("The music directory is missing; the index has been preserved")
    tracks = []
    issues = []
    baseline = [track.relative_path for track in store.list_tracks()]
    pending = store.pending_import_roots()
    source_names = store.import_source_names()

    def traversal_error(error: OSError) -> None:
        raise error

    for directory, folders, filenames in os.walk(music, followlinks=False, onerror=traversal_error):
        folder = Path(directory)
        for name in folders[:]:
            child = folder / name
            if child.relative_to(layout.root).as_posix() in pending:
                folders.remove(name)
                continue
            if child.is_symlink() or child.is_junction():
                folders.remove(name)
                issues.append(ScanIssue(child.relative_to(layout.root).as_posix(), "Linked folder"))
            else:
                layout.relative_path(child)
        for name in sorted(filenames):
            path = folder / name
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            relative = path.relative_to(layout.root).as_posix()
            try:
                if path.is_symlink() or path.is_junction():
                    raise ValueError("Linked file")
                layout.resolve_relative(relative)
                if not path.is_file():
                    raise ValueError("Not a regular audio file")
                original_name = source_names.get(relative)
                tracks.append(
                    read_track(
                        path,
                        relative,
                        fallback_title=Path(original_name).stem if original_name else None,
                    )
                )
            except (OSError, ValueError, mutagen.MutagenError) as error:
                issues.append(ScanIssue(relative, str(error)))
    counts = Counter(track.sha256 for track in tracks)
    duplicates = sum(count - 1 for count in counts.values())
    missing = store.replace_scan(tracks, [asdict(issue) for issue in issues], duplicates, baseline)
    return ScanReport(len(tracks), missing, duplicates, tuple(issues))
