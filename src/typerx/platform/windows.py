from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes
from dataclasses import dataclass
from typing import Callable

LOGGER = logging.getLogger(__name__)
IS_WINDOWS = hasattr(ctypes, "windll")

if IS_WINDOWS:
    user32 = ctypes.windll.user32

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", INPUT_UNION)]


class FocusChangedError(RuntimeError):
    pass


class UnsupportedPlatformError(RuntimeError):
    pass


class WindowsInput:
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    VK_RETURN = 0x0D
    VK_BACK = 0x08

    def __init__(self, target_window: int) -> None:
        if not IS_WINDOWS:
            raise UnsupportedPlatformError("TyperX input is available on Windows only")
        self.target_window = target_window

    @staticmethod
    def foreground_window() -> int:
        return int(user32.GetForegroundWindow()) if IS_WINDOWS else 0

    def assert_focus(self) -> None:
        if self.foreground_window() != self.target_window:
            raise FocusChangedError("Активное окно изменилось, ввод безопасно остановлен")

    def write(self, char: str) -> None:
        self.assert_focus()
        codepoint = ord(char)
        down = self._unicode_input(codepoint, 0)
        up = self._unicode_input(codepoint, self.KEYEVENTF_KEYUP)
        self._send((INPUT * 2)(down, up))

    def enter(self) -> None:
        self._virtual_key(self.VK_RETURN)

    def backspace(self) -> None:
        self._virtual_key(self.VK_BACK)

    def _virtual_key(self, key: int) -> None:
        self.assert_focus()
        down = INPUT(type=1, ki=KEYBDINPUT(wVk=key))
        up = INPUT(type=1, ki=KEYBDINPUT(wVk=key, dwFlags=self.KEYEVENTF_KEYUP))
        self._send((INPUT * 2)(down, up))

    def _unicode_input(self, codepoint: int, flags: int) -> INPUT:
        return INPUT(type=1, ki=KEYBDINPUT(wScan=codepoint, dwFlags=self.KEYEVENTF_UNICODE | flags))

    @staticmethod
    def _send(inputs: object) -> None:
        count = len(inputs)  # type: ignore[arg-type]
        sent = user32.SendInput(count, inputs, ctypes.sizeof(INPUT))
        if sent != count:
            raise OSError(ctypes.get_last_error(), "Windows rejected synthetic input")


@dataclass(slots=True)
class GlobalHotkeys:
    on_start: Callable[[], None]
    on_stop: Callable[[], None]
    _thread: threading.Thread | None = None
    _thread_id: int = 0

    def start(self) -> None:
        if not IS_WINDOWS or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="typerx-hotkeys", daemon=True)
        self._thread.start()

    def close(self) -> None:
        if IS_WINDOWS and self._thread_id:
            user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)
        if self._thread:
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, 1, 0, 0x77):  # F8
            LOGGER.warning("F8 is already registered by another application")
        if not user32.RegisterHotKey(None, 2, 0, 0x78):  # F9
            LOGGER.warning("F9 is already registered by another application")
        message = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == 0x0312:
                    (self.on_start if message.wParam == 1 else self.on_stop)()
        finally:
            user32.UnregisterHotKey(None, 1)
            user32.UnregisterHotKey(None, 2)
