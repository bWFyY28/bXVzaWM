import json
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from helpers import write_wave

from bxvzm.config import Settings
from bxvzm.database import LibraryStore
from bxvzm.indexing import scan_library
from bxvzm.library import LibraryLayout
from bxvzm.playback import MpvPlayer, PlaybackError
from bxvzm.service import (
    MAX_MESSAGE,
    PlaybackController,
    ServiceError,
    ServiceServer,
    _instance_lock,
    request,
    serve,
)


class FakePlayer:
    def __init__(self) -> None:
        self.loads = []
        self.closed = False
        self.values = {"position": 0, "duration": 60, "paused": True, "idle": True, "volume": 75}

    def load(self, path, position=0, volume=75):
        self.loads.append((path, position, volume))
        self.values.update(position=position, volume=volume, paused=False, idle=False)

    def command(self, *arguments):
        if arguments == ("cycle", "pause"):
            self.values["paused"] = not self.values["paused"]
        elif arguments[:2] == ("set_property", "volume"):
            self.values["volume"] = arguments[2]
        elif arguments[0] == "seek":
            self.values["position"] += arguments[1]

    def status(self):
        return self.values.copy()

    def close(self):
        self.closed = True


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.layout = LibraryLayout.at(self.base / "data/library", app_root=self.base)
        self.store = LibraryStore(self.layout)
        self.store.initialize()
        write_wave(self.layout.music / "song.wav")
        scan_library(self.store)
        self.player = FakePlayer()
        self.controller = PlaybackController(self.store, self.player)

    def test_shared_play_pause_seek_volume_and_restore_without_autoplay(self) -> None:
        self.controller.dispatch("play", {"path": "music/song.wav"})
        self.controller.dispatch("seek", {"seconds": 12})
        self.controller.dispatch("volume", {"value": 60})
        self.assertTrue(self.controller.dispatch("pause", {})["paused"])
        self.controller.close()
        self.assertTrue(self.player.closed)
        with self.assertRaises(ServiceError):
            self.controller.dispatch("play", {"path": "music/song.wav"})
        self.assertEqual(len(self.player.loads), 1)
        replacement = FakePlayer()
        reopened = PlaybackController(self.store, replacement)
        self.assertEqual(reopened.status()["position"], 12)
        self.assertEqual(replacement.loads, [])
        reopened.dispatch("pause", {})
        self.assertEqual(replacement.loads[0][1:], (12, 60))

    def test_unindexed_missing_and_external_paths_never_reach_player(self) -> None:
        for path in ("../external.wav", "music/missing.wav", "C:/external.wav"):
            with self.assertRaises(ValueError):
                self.controller.dispatch("play", {"path": path})
        (self.layout.music / "song.wav").unlink()
        with self.assertRaises(ValueError):
            self.controller.dispatch("play", {"path": "music/song.wav"})
        self.assertEqual(self.player.loads, [])

    def test_only_explicit_bounded_player_commands_are_allowed(self) -> None:
        for command, arguments in (
            ("run", {"command": "arbitrary program"}),
            ("volume", {"value": 101}),
            ("volume", {"value": float("nan")}),
            ("seek", {"seconds": 4000}),
            ("play", {"path": []}),
        ):
            with self.assertRaises(ValueError):
                self.controller.dispatch(command, arguments)

    def test_single_instance_lock(self) -> None:
        with _instance_lock(self.layout) as first:
            self.assertTrue(first)
            with _instance_lock(self.layout) as second:
                self.assertFalse(second)
        with _instance_lock(self.layout) as third:
            self.assertTrue(third)

    def test_local_json_auth_size_limit_and_exit(self) -> None:
        stop = threading.Event()
        with ServiceServer(self.controller, stop) as server:
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            self.layout.resolve_relative(".service.json").write_text(
                json.dumps({"port": server.server_address[1], "token": server.token})
            )
            try:
                self.assertEqual(server.server_address[0], "127.0.0.1")
                self.assertEqual(
                    request(self.layout, "play", path="music/song.wav")["title"], "Circles"
                )
                with self.assertRaises(ServiceError):
                    request(self.layout, "run")
                for payload in (
                    b'{"token":"wrong","command":"exit"}\n',
                    b"x" * (MAX_MESSAGE + 1) + b"\n",
                    b"[]\n",
                ):
                    with socket.create_connection(server.server_address, timeout=2) as connection:
                        connection.sendall(payload)
                        with connection.makefile("rb") as stream:
                            result = json.loads(stream.readline())
                    self.assertFalse(result["ok"])
                    self.assertFalse(stop.is_set())
                request(self.layout, "exit")
                self.assertTrue(stop.is_set())
            finally:
                server.shutdown()
                thread.join(timeout=3)

    def test_service_lifecycle_cleans_endpoint_and_player(self) -> None:
        settings = Settings(self.layout.root, self.base / "data/config.json", self.base)
        errors = []

        def run():
            try:
                serve(settings, tray=False)
            except Exception as error:
                errors.append(error)

        with patch("bxvzm.service.MpvPlayer", return_value=self.player):
            thread = threading.Thread(target=run)
            thread.start()
            deadline = time.monotonic() + 5
            try:
                while time.monotonic() < deadline:
                    try:
                        request(self.layout, "status")
                        break
                    except ServiceError:
                        time.sleep(0.05)
                request(self.layout, "exit")
            finally:
                thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertFalse(self.layout.resolve_relative(".service.json").exists())
        self.assertTrue(self.player.closed)

    def test_missing_mpv_does_not_spawn_or_disable_browsing(self) -> None:
        player = MpvPlayer(self.layout, self.base)
        with patch("bxvzm.playback.shutil.which", return_value=None):
            with self.assertRaisesRegex(PlaybackError, "mpv is missing"):
                player.load(self.layout.music / "song.wav")
        self.assertEqual(len(self.store.list_tracks()), 1)
        self.assertIsNone(player.process)

    @unittest.skipUnless(os.name == "nt", "Windows IPC and tray behavior")
    def test_windows_pipe_not_ready_is_retried(self) -> None:
        import pywintypes

        player = MpvPlayer(self.layout, self.base)
        process = MagicMock()
        process.poll.return_value = None
        pipe = MagicMock()
        with (
            patch("bxvzm.playback.shutil.which", return_value="mpv.exe"),
            patch("bxvzm.playback.subprocess.Popen", return_value=process),
            patch(
                "win32file.CreateFile",
                side_effect=[pywintypes.error(2, "CreateFile", "not ready"), pipe],
            ),
            patch("bxvzm.playback.time.sleep"),
        ):
            player._start()
        self.assertIs(player.pipe, pipe)
        player.close()
        pipe.Close.assert_called_once()
        process.terminate.assert_called_once()

    @unittest.skipUnless(os.name == "nt", "Windows tray behavior")
    def test_tray_close_requests_shutdown_without_destroying_window_early(self) -> None:
        import win32con

        from bxvzm.tray import TrayIcon

        icon = TrayIcon.__new__(TrayIcon)
        icon.stop = threading.Event()
        icon.win32gui = MagicMock()
        icon.message = win32con.WM_USER + 20
        icon.restart_message = 99999
        self.assertEqual(icon._event(10, win32con.WM_CLOSE, 0, 0), 0)
        self.assertTrue(icon.stop.is_set())
        icon.win32gui.DefWindowProc.assert_not_called()
