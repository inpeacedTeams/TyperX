from __future__ import annotations

import ctypes
import logging
import threading
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass

LOGGER = logging.getLogger(__name__)
IS_WINDOWS = hasattr(ctypes, "WinDLL")

if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", INPUT_UNION)]

    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.VkKeyScanExW.argtypes = (wintypes.WCHAR, wintypes.HKL)
    user32.VkKeyScanExW.restype = ctypes.c_short
    user32.MapVirtualKeyExW.argtypes = (wintypes.UINT, wintypes.UINT, wintypes.HKL)
    user32.MapVirtualKeyExW.restype = wintypes.UINT
    user32.GetKeyboardLayout.argtypes = (wintypes.DWORD,)
    user32.GetKeyboardLayout.restype = wintypes.HKL
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD


class FocusChangedError(RuntimeError):
    pass


class UnsupportedPlatformError(RuntimeError):
    pass


class WindowsInput:
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    MAPVK_VK_TO_VSC = 0
    VK_RETURN = 0x0D
    VK_BACK = 0x08
    VK_SHIFT = 0x10
    VK_CONTROL = 0x11
    VK_MENU = 0x12

    def __init__(self, target_window: int) -> None:
        if not IS_WINDOWS:
            raise UnsupportedPlatformError("TyperX input is available on Windows only")
        self.target_window = target_window

    def _get_hkl(self) -> int:
        """Get the keyboard layout handle for the target window's thread."""
        tid = user32.GetWindowThreadProcessId(self.target_window, None)
        return user32.GetKeyboardLayout(tid)

    @staticmethod
    def foreground_window() -> int:
        return int(user32.GetForegroundWindow()) if IS_WINDOWS else 0

    def assert_focus(self) -> None:
        if self.foreground_window() != self.target_window:
            raise FocusChangedError("Активное окно изменилось, ввод безопасно остановлен")

    def write(self, char: str) -> None:
        """Type a character using real VK + scan-code keystrokes.

        Falls back to Unicode input only for characters absent from the
        active keyboard layout.
        """
        self.assert_focus()
        hkl = self._get_hkl()
        vk_result = user32.VkKeyScanExW(char, hkl)

        if vk_result == -1:
            self._write_unicode(char)
            return

        vk = vk_result & 0xFF
        shift_state = (vk_result >> 8) & 0xFF
        scan = user32.MapVirtualKeyExW(vk, self.MAPVK_VK_TO_VSC, hkl)

        modifiers: list[int] = []
        if shift_state & 1:
            modifiers.append(self.VK_SHIFT)
        if shift_state & 2:
            modifiers.append(self.VK_CONTROL)
        if shift_state & 4:
            modifiers.append(self.VK_MENU)

        events: list[INPUT] = []
        for mod in modifiers:
            mod_scan = user32.MapVirtualKeyExW(mod, self.MAPVK_VK_TO_VSC, hkl)
            events.append(INPUT(type=1, ki=KEYBDINPUT(wVk=mod, wScan=mod_scan)))

        events.append(INPUT(type=1, ki=KEYBDINPUT(wVk=vk, wScan=scan)))
        events.append(INPUT(type=1, ki=KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=self.KEYEVENTF_KEYUP)))

        for mod in reversed(modifiers):
            mod_scan = user32.MapVirtualKeyExW(mod, self.MAPVK_VK_TO_VSC, hkl)
            events.append(INPUT(type=1, ki=KEYBDINPUT(wVk=mod, wScan=mod_scan, dwFlags=self.KEYEVENTF_KEYUP)))

        self._send(events)

    def _write_unicode(self, char: str) -> None:
        """Fallback for characters not on the active keyboard layout."""
        utf16 = char.encode("utf-16-le", errors="strict")
        units = [int.from_bytes(utf16[i : i + 2], "little") for i in range(0, len(utf16), 2)]
        events: list[INPUT] = []
        for unit in units:
            events.append(self._unicode_input(unit, 0))
            events.append(self._unicode_input(unit, self.KEYEVENTF_KEYUP))
        self._send(events)

    def enter(self) -> None:
        self._virtual_key(self.VK_RETURN)

    def backspace(self) -> None:
        self._virtual_key(self.VK_BACK)

    def _virtual_key(self, key: int) -> None:
        self.assert_focus()
        scan = user32.MapVirtualKeyExW(key, self.MAPVK_VK_TO_VSC, self._get_hkl())
        self._send([INPUT(type=1, ki=KEYBDINPUT(wVk=key, wScan=scan)), INPUT(type=1, ki=KEYBDINPUT(wVk=key, wScan=scan, dwFlags=self.KEYEVENTF_KEYUP))])

    def _unicode_input(self, codepoint: int, flags: int) -> INPUT:
        return INPUT(type=1, ki=KEYBDINPUT(wScan=codepoint, dwFlags=self.KEYEVENTF_UNICODE | flags))

    @staticmethod
    def _send(events: list[INPUT]) -> None:
        inputs = (INPUT * len(events))(*events)
        sent = user32.SendInput(len(inputs), inputs, ctypes.sizeof(INPUT))
        if sent != len(inputs):
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
        self._thread_id = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, 1, 0, 0x77):
            LOGGER.warning("F8 is already registered by another application")
        if not user32.RegisterHotKey(None, 2, 0, 0x78):
            LOGGER.warning("F9 is already registered by another application")
        message = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == 0x0312:
                    (self.on_start if message.wParam == 1 else self.on_stop)()
        finally:
            user32.UnregisterHotKey(None, 1)
            user32.UnregisterHotKey(None, 2)
