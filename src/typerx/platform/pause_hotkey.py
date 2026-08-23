from __future__ import annotations

import ctypes
import logging
import threading
from collections.abc import Callable
from ctypes import wintypes

LOGGER = logging.getLogger(__name__)
IS_WINDOWS = hasattr(ctypes, "WinDLL")

if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


class PauseHotkey:
    HOTKEY_ID = 10
    VK_F10 = 0x79
    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012

    def __init__(self, on_toggle: Callable[[], None]) -> None:
        self.on_toggle = on_toggle
        self._thread: threading.Thread | None = None
        self._thread_id = 0

    def start(self) -> None:
        if not IS_WINDOWS or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="typerx-pause-hotkey", daemon=True)
        self._thread.start()

    def close(self) -> None:
        if IS_WINDOWS and self._thread_id:
            user32.PostThreadMessageW(self._thread_id, self.WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, self.HOTKEY_ID, 0, self.VK_F10):
            LOGGER.warning("F10 is already registered by another application")
            return
        message = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == self.WM_HOTKEY and message.wParam == self.HOTKEY_ID:
                    self.on_toggle()
        finally:
            user32.UnregisterHotKey(None, self.HOTKEY_ID)
