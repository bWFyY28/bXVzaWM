"""One lazy mpv subprocess, using bounded JSON IPC requests."""

import json
import os
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from bxvzm.library import LibraryLayout

IPC_ERRORS = (OSError, ValueError)
if os.name == "nt":
    import pywintypes

    IPC_ERRORS += (pywintypes.error,)


class PlaybackError(RuntimeError):
    pass


class MpvPlayer:
    def __init__(self, layout: LibraryLayout, app_root: Path) -> None:
        self.layout = layout
        self.app_root = app_root
        self.process: subprocess.Popen | None = None
        self.pipe: Any = None
        self.socket: socket.socket | None = None
        self.buffer = b""
        self.request_id = 0
        self.endpoint = (
            rf"\\.\pipe\bxvzm-{uuid.uuid4().hex}"
            if os.name == "nt"
            else str(layout.resolve_relative(".mpv.sock"))
        )

    def _start(self) -> None:
        if self.process and self.process.poll() is None:
            return
        self.close()
        bundled = self.app_root / "data" / "tools" / ("mpv.exe" if os.name == "nt" else "mpv")
        if not bundled.resolve().is_relative_to(self.app_root / "data"):
            raise PlaybackError("Portable mpv must stay inside data/")
        executable = str(bundled) if bundled.is_file() else shutil.which("mpv")
        if not executable:
            raise PlaybackError("mpv is missing. Put mpv.exe in data/tools/ or add mpv to PATH.")
        self.process = subprocess.Popen(
            [
                executable,
                "--no-config",
                "--idle=yes",
                "--no-video",
                "--no-terminal",
                "--input-media-keys=no",
                "--audio-display=no",
                f"--input-ipc-server={self.endpoint}",
            ],
            cwd=self.layout.root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and self.process.poll() is None:
            try:
                if os.name == "nt":
                    import win32con
                    import win32file

                    self.pipe = win32file.CreateFile(
                        self.endpoint,
                        win32con.GENERIC_READ | win32con.GENERIC_WRITE,
                        0,
                        None,
                        win32con.OPEN_EXISTING,
                        0,
                        None,
                    )
                else:
                    self.socket = socket.socket(socket.AF_UNIX)
                    self.socket.settimeout(2)
                    self.socket.connect(self.endpoint)
                return
            except IPC_ERRORS:
                if self.socket:
                    self.socket.close()
                    self.socket = None
                time.sleep(0.05)
        self.close()
        raise PlaybackError("mpv failed to start its local IPC endpoint")

    def _read_line(self) -> bytes:
        deadline = time.monotonic() + 2
        while b"\n" not in self.buffer:
            if len(self.buffer) > 1024 * 1024:
                raise PlaybackError("mpv response is too large")
            if time.monotonic() >= deadline:
                raise PlaybackError("mpv did not reply in time")
            if os.name == "nt":
                import win32file
                import win32pipe

                _, available, _ = win32pipe.PeekNamedPipe(self.pipe, 0)
                if not available:
                    time.sleep(0.01)
                    continue
                _, chunk = win32file.ReadFile(self.pipe, min(available, 65536))
            else:
                assert self.socket is not None
                chunk = self.socket.recv(65536)
            if not chunk:
                raise PlaybackError("mpv disconnected")
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b"\n", 1)
        return line

    def command(self, *command: Any) -> Any:
        self._start()
        self.request_id += 1
        payload = json.dumps({"command": command, "request_id": self.request_id}).encode() + b"\n"
        try:
            if os.name == "nt":
                import win32file

                win32file.WriteFile(self.pipe, payload)
            else:
                assert self.socket is not None
                self.socket.sendall(payload)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                response = json.loads(self._read_line())
                if response.get("request_id") == self.request_id:
                    if response.get("error") != "success":
                        raise PlaybackError(f"mpv: {response.get('error', 'unknown error')}")
                    return response.get("data")
            raise PlaybackError("mpv request timed out")
        except IPC_ERRORS as error:
            self.close()
            raise PlaybackError(f"Cannot communicate with mpv: {error}") from error

    def load(self, path: Path, position: float = 0, volume: float = 75) -> None:
        self.command("set_property", "volume", volume)
        self.command("set_property", "pause", False)
        self.command("loadfile", str(path), "replace", -1, {"start": str(position)})

    def status(self) -> dict[str, Any]:
        if not self.process:
            return {"position": 0, "duration": 0, "paused": True, "idle": True, "volume": 75}
        if self.process.poll() is not None:
            self.close()
            raise PlaybackError("mpv exited; select a track to restart playback")
        values = {}
        for name in ("time-pos", "duration", "pause", "idle-active", "volume"):
            try:
                values[name] = self.command("get_property", name)
            except PlaybackError as error:
                # Properties are unavailable while no file is loaded. Other
                # failures must not silently restart a disconnected player.
                if "property unavailable" not in str(error):
                    raise
                values[name] = None
        return {
            "position": values["time-pos"] or 0,
            "duration": values["duration"] or 0,
            "paused": bool(values["pause"]),
            "idle": bool(values["idle-active"]),
            "volume": values["volume"] if values["volume"] is not None else 75,
        }

    def close(self) -> None:
        if self.pipe is not None:
            self.pipe.Close()
            self.pipe = None
        if self.socket is not None:
            self.socket.close()
            self.socket = None
        if self.process is not None:
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
            self.process = None
        self.buffer = b""
        if os.name != "nt":
            self.layout.resolve_relative(".mpv.sock").unlink(missing_ok=True)
