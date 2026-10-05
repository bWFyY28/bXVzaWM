"""Native Windows tray lifecycle with a static monochrome letter b."""

import ctypes
import threading
from ctypes import wintypes


class TrayIcon:
    def __init__(self, stop: threading.Event) -> None:
        import win32api
        import win32con
        import win32gui

        self.stop = stop
        self.win32gui = win32gui
        self.message = win32con.WM_USER + 20
        self.restart_message = win32gui.RegisterWindowMessage("TaskbarCreated")
        instance = win32api.GetModuleHandle(None)
        window_class = win32gui.WNDCLASS()
        window_class.hInstance = instance
        window_class.lpszClassName = "bXVzaVMTray"
        window_class.lpfnWndProc = self._event
        self.class_id = win32gui.RegisterClass(window_class)
        self.window = win32gui.CreateWindow(
            self.class_id, "bXVzaVM", 0, 0, 0, 0, 0, 0, 0, instance, None
        )
        # Transparent background with a plain white b; no images or animations.
        rows = ("10000", "10000", "10110", "11001", "10001", "11001", "10110")
        and_mask, xor_mask = bytearray(b"\xff" * 32), bytearray(32)
        for y, row in enumerate(rows, 4):
            for x, pixel in enumerate(row, 5):
                if pixel == "1":
                    index, bit = y * 2 + x // 8, 1 << (7 - x % 8)
                    and_mask[index] &= 255 ^ bit
                    xor_mask[index] |= bit
        create_icon = ctypes.windll.user32.CreateIcon
        create_icon.argtypes = [
            wintypes.HINSTANCE,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_byte,
            ctypes.c_byte,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        create_icon.restype = wintypes.HICON
        self.icon = create_icon(
            instance,
            16,
            16,
            1,
            1,
            ctypes.create_string_buffer(bytes(and_mask)),
            ctypes.create_string_buffer(bytes(xor_mask)),
        )
        if not self.icon:
            self.close()
            raise OSError("Cannot create the monochrome tray icon")
        self._add()

    def _add(self) -> None:
        gui = self.win32gui
        gui.Shell_NotifyIcon(
            gui.NIM_ADD,
            (
                self.window,
                0,
                gui.NIF_ICON | gui.NIF_MESSAGE | gui.NIF_TIP,
                self.message,
                self.icon,
                "bXVzaVM | Right-click to exit",
            ),
        )

    def _event(self, window: int, message: int, wparam: int, lparam: int) -> int:
        import win32api
        import win32con

        gui = self.win32gui
        if message == self.restart_message:
            self._add()
        elif message == self.message and lparam == win32con.WM_RBUTTONUP:
            menu = gui.CreatePopupMenu()
            try:
                gui.AppendMenu(menu, win32con.MF_STRING, 1, "Exit bXVzaVM")
                gui.SetForegroundWindow(window)
                x, y = gui.GetCursorPos()
                selected = gui.TrackPopupMenu(
                    menu,
                    win32con.TPM_RETURNCMD | win32con.TPM_RIGHTBUTTON,
                    x,
                    y,
                    0,
                    window,
                    None,
                )
                if selected == 1:
                    self.stop.set()
                win32api.PostMessage(window, win32con.WM_NULL, 0, 0)
            finally:
                gui.DestroyMenu(menu)
        elif message in (win32con.WM_CLOSE, win32con.WM_ENDSESSION):
            self.stop.set()
            # Leave destruction to close(), after the service loop stops.
            return 0
        return gui.DefWindowProc(window, message, wparam, lparam)

    def pump(self) -> None:
        self.win32gui.PumpWaitingMessages()

    def close(self) -> None:
        import win32api

        self.win32gui.Shell_NotifyIcon(self.win32gui.NIM_DELETE, (self.window, 0))
        if self.icon:
            self.win32gui.DestroyIcon(self.icon)
        self.win32gui.DestroyWindow(self.window)
        self.win32gui.UnregisterClass(self.class_id, win32api.GetModuleHandle(None))
