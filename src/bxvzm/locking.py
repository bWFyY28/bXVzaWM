"""OS-owned library locks; a crash releases ownership without stale PID guessing."""

import hashlib
import os
from collections.abc import Iterator
from contextlib import contextmanager

from bxvzm.library import LibraryLayout


@contextmanager
def exclusive_lock(layout: LibraryLayout, name: str) -> Iterator[bool]:
    path = layout.resolve_relative(name)
    if path != layout.root / name or path.is_symlink() or path.is_junction():
        raise ValueError("Library lock files must not contain links")
    if os.name == "nt":
        import win32api
        import win32event
        import winerror

        identity = hashlib.sha256((str(layout.root).casefold() + name).encode()).hexdigest()
        handle = win32event.CreateMutex(None, False, f"Local\\bxvzm-{identity}")
        acquired = win32api.GetLastError() != winerror.ERROR_ALREADY_EXISTS
        try:
            yield acquired
        finally:
            handle.Close()
    else:
        import fcntl

        with path.open("a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
            else:
                yield True
