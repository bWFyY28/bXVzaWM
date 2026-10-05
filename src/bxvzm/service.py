"""Per-library background playback with a bounded, authenticated local JSON API."""

import hashlib
import json
import math
import os
import secrets
import socket
import socketserver
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from bxvzm.config import Settings
from bxvzm.database import LibraryStore
from bxvzm.library import LibraryLayout
from bxvzm.playback import MpvPlayer, PlaybackError

MAX_MESSAGE = 65536


class ServiceError(RuntimeError):
    pass


def _service_path(layout: LibraryLayout, name: str) -> Path:
    path = layout.root / name
    layout.resolve_relative(name)
    if path.is_symlink() or path.is_junction():
        raise ValueError("Service files must not be links")
    return path


def request(layout: LibraryLayout, command: str, **arguments: Any) -> dict:
    """Contact an existing service; never start one as a side effect of status."""
    try:
        endpoint = json.loads(_service_path(layout, ".service.json").read_text(encoding="utf-8"))
        port, token = endpoint["port"], endpoint["token"]
        if type(port) is not int or not 1 <= port <= 65535 or not isinstance(token, str):
            raise ValueError("Invalid service endpoint")
        payload = json.dumps({"token": token, "command": command, **arguments}).encode() + b"\n"
        if len(payload) > MAX_MESSAGE:
            raise ValueError("Service request is too large")
        with socket.create_connection(("127.0.0.1", port), timeout=8) as connection:
            connection.sendall(payload)
            with connection.makefile("rb") as stream:
                raw = stream.readline(MAX_MESSAGE + 1)
        if not raw.endswith(b"\n") or len(raw) > MAX_MESSAGE:
            raise ValueError("Invalid service response")
        response = json.loads(raw)
        if not isinstance(response, dict):
            raise ValueError("Invalid service response")
        if not response.get("ok"):
            raise ServiceError(response.get("error", "Service command failed"))
        return response
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ServiceError("Background service is unavailable. Start it with --daemon.") from error


def start_service(settings: Settings) -> dict:
    layout = LibraryLayout.at(settings.library_root, settings.app_root)
    try:
        return request(layout, "status")
    except ServiceError:
        pass
    executable = Path(sys.executable)
    if os.name == "nt":
        executable = executable.with_name("pythonw.exe")
    env = os.environ.copy()
    env.update(PYTHONPATH=str(settings.app_root / "src"), PYTHONDONTWRITEBYTECODE="1")
    with _service_path(layout, ".service.log").open("ab") as log:
        child = subprocess.Popen(
            [
                str(executable),
                "-m",
                "bxvzm",
                "--serve",
                "--library",
                str(settings.library_root),
                "--config",
                str(settings.config_file),
            ],
            cwd=settings.app_root,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            creationflags=(subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
            if os.name == "nt"
            else 0,
            start_new_session=os.name != "nt",
        )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            return request(layout, "status")
        except ServiceError:
            if child.poll() not in (None, 0):
                break
            time.sleep(0.1)
    raise ServiceError("Service did not start. See the library's .service.log.")


@contextmanager
def _instance_lock(layout: LibraryLayout):
    """The OS releases ownership even when the process crashes."""
    if os.name == "nt":
        import win32api
        import win32event
        import winerror

        identity = hashlib.sha256(str(layout.root).casefold().encode()).hexdigest()
        handle = win32event.CreateMutex(None, False, f"Local\\bxvzm-{identity}")
        acquired = win32api.GetLastError() != winerror.ERROR_ALREADY_EXISTS
        try:
            yield acquired
        finally:
            handle.Close()
    else:
        import fcntl

        with _service_path(layout, ".service.lock").open("a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
            else:
                yield True


class PlaybackController:
    """Serialize player commands; restore selection without starting mpv."""

    def __init__(self, store: LibraryStore, player: MpvPlayer) -> None:
        self.store = store
        self.player = player
        self.lock = threading.RLock()
        saved = store.load_state("playback", {})
        if not isinstance(saved, dict):
            saved = {}
        self.path = saved.get("path", "") if isinstance(saved.get("path", ""), str) else ""

        def number(key: str, default: float, maximum: float) -> float:
            value = saved.get(key, default)
            return (
                value
                if type(value) in (int, float) and math.isfinite(value) and 0 <= value <= maximum
                else default
            )

        self.position = number("position", 0, 10**9)
        self.volume = number("volume", 75, 100)
        self.loaded = False
        self.error = ""
        self.closed = False

    def status(self) -> dict:
        try:
            values = self.player.status() if self.loaded else None
        except PlaybackError as error:
            self.loaded = False
            self.error = str(error)
            self.player.close()
            values = None
        if values is None:
            values = {
                "position": self.position,
                "duration": 0,
                "volume": self.volume,
                "paused": True,
                "idle": True,
            }
        self.position, self.volume = values["position"], values["volume"]
        track = next(
            (track for track in self.store.list_tracks() if track.relative_path == self.path), None
        )
        return {
            "ok": True,
            "path": self.path,
            "title": track.title if track else "No track loaded",
            "artist": track.artist if track else "",
            "error": self.error,
            **values,
        }

    def _play(self, relative: str, position: float = 0) -> None:
        track = next(
            (track for track in self.store.list_tracks() if track.relative_path == relative), None
        )
        if track is None or not track.available:
            raise ValueError("Track is missing or not indexed; rescan music/ first")
        path = self.store.layout.resolve_relative(relative)
        music = self.store.layout.resolve_relative("music")
        if not path.is_relative_to(music) or not path.is_file():
            raise ValueError("Track must be an existing local file inside music/")
        self.player.load(path, position, self.volume)
        self.path, self.position, self.loaded, self.error = relative, position, True, ""

    def dispatch(self, command: str, arguments: dict) -> dict:
        with self.lock:
            if self.closed:
                raise ServiceError("Background service is exiting")
            if command == "play":
                relative = arguments.get("path")
                if not isinstance(relative, str):
                    raise ValueError("A relative track path is required")
                self._play(relative)
            elif command == "pause":
                if not self.loaded:
                    if not self.path:
                        raise ValueError("Select a track first")
                    self._play(self.path, self.position)
                else:
                    self.player.command("cycle", "pause")
            elif command == "seek":
                amount = arguments.get("seconds")
                if type(amount) not in (int, float) or not -3600 <= amount <= 3600:
                    raise ValueError("Seek must be between -3600 and 3600 seconds")
                if not self.loaded:
                    raise ValueError("Select a track first")
                self.player.command("seek", amount, "relative")
            elif command == "volume":
                volume = arguments.get("value")
                if type(volume) not in (int, float) or not 0 <= volume <= 100:
                    raise ValueError("Volume must be between 0 and 100")
                self.volume = volume
                if self.loaded:
                    self.player.command("set_property", "volume", volume)
            elif command != "status":
                raise ValueError("Unknown service command")
            values = self.status()
            if command != "status":
                self.save()
            return values

    def save(self) -> None:
        self.store.save_state(
            "playback",
            {
                "path": self.path,
                "position": self.position,
                "volume": self.volume,
            },
        )

    def close(self) -> None:
        with self.lock:
            if self.closed:
                return
            self.closed = True
            try:
                self.status()
                self.save()
            finally:
                self.player.close()


class ServiceServer(socketserver.ThreadingTCPServer):
    daemon_threads = True

    def __init__(self, controller: PlaybackController, stop: threading.Event) -> None:
        self.controller = controller
        self.stop_event = stop
        self.token = secrets.token_hex(32)
        super().__init__(("127.0.0.1", 0), ServiceHandler)


class ServiceHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        self.connection.settimeout(3)
        server: ServiceServer = self.server  # type: ignore[assignment]
        try:
            raw = self.rfile.readline(MAX_MESSAGE + 1)
            if len(raw) > MAX_MESSAGE or not raw.endswith(b"\n"):
                raise ValueError("Request is too large or incomplete")
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object")
            token = payload.get("token")
            if not isinstance(token, str) or not secrets.compare_digest(token, server.token):
                raise ValueError("Unauthorized")
            command = payload.get("command")
            if command == "exit":
                response = {"ok": True}
                server.stop_event.set()
            else:
                response = server.controller.dispatch(command, payload)
        except (OSError, ValueError, RuntimeError) as error:
            response = {"ok": False, "error": str(error)}
        try:
            self.wfile.write(json.dumps(response, allow_nan=False).encode() + b"\n")
        except OSError:
            pass


def serve(settings: Settings, *, tray: bool = True) -> int:
    layout = LibraryLayout.at(settings.library_root, settings.app_root)
    store = LibraryStore(layout)
    store.initialize()
    with _instance_lock(layout) as acquired:
        if not acquired:
            return 0
        controller = PlaybackController(store, MpvPlayer(layout, settings.app_root))
        stop = threading.Event()
        with ServiceServer(controller, stop) as server:
            endpoint = _service_path(layout, ".service.json")
            temporary = _service_path(layout, ".service.json.tmp")
            server_thread = None
            tray_icon = None
            last_save = 0.0
            try:
                if tray and os.name == "nt":
                    from bxvzm.tray import TrayIcon

                    tray_icon = TrayIcon(stop)
                descriptor = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
                with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                    json.dump(
                        {
                            "port": server.server_address[1],
                            "token": server.token,
                            "pid": os.getpid(),
                        },
                        stream,
                    )
                temporary.replace(endpoint)
                server_thread = threading.Thread(target=server.serve_forever, daemon=True)
                server_thread.start()
                while not stop.wait(0.1):
                    if tray_icon:
                        tray_icon.pump()
                    # Sample position and persist it periodically, independently of the TUI.
                    if time.monotonic() - last_save > 5:
                        with controller.lock:
                            controller.status()
                            controller.save()
                        last_save = time.monotonic()
            finally:
                if server_thread:
                    server.shutdown()
                    server_thread.join(timeout=3)
                try:
                    if tray_icon:
                        tray_icon.close()
                finally:
                    try:
                        controller.close()
                    finally:
                        endpoint.unlink(missing_ok=True)
    return 0
