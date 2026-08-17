from __future__ import annotations

import ctypes
import random
import time
from ctypes import wintypes

from interception.constants import KeyFlag
from interception.interception import Interception
from interception.strokes import KeyStroke

from typerx.platform.windows import FocusChangedError, UnsupportedPlatformError

IS_WINDOWS = hasattr(ctypes, "WinDLL")

if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.GetKeyboardLayout.argtypes = (wintypes.DWORD,)
    user32.GetKeyboardLayout.restype = wintypes.HKL
    user32.VkKeyScanExW.argtypes = (wintypes.WCHAR, wintypes.HKL)
    user32.VkKeyScanExW.restype = ctypes.c_short
    user32.MapVirtualKeyExW.argtypes = (wintypes.UINT, wintypes.UINT, wintypes.HKL)
    user32.MapVirtualKeyExW.restype = wintypes.UINT


class DriverNotReadyError(RuntimeError):
    pass


class InterceptionKeyboard:
    MAPVK_VK_TO_VSC_EX = 4
    VK_BACK = 0x08
    VK_RETURN = 0x0D
    VK_SHIFT = 0x10
    VK_CONTROL = 0x11
    VK_MENU = 0x12

    def __init__(self, target_window: int) -> None:
        if not IS_WINDOWS:
            raise UnsupportedPlatformError("TyperX input is available on Windows only")
        self.target_window = target_window
        self._rng = random.Random()
        self._context = Interception()
        if not self._context.valid:
            raise DriverNotReadyError(
                "Interception driver is not installed. Run install_driver.bat as administrator, "
                "reboot Windows, then start TyperX again."
            )
        self._keyboard = self._find_keyboard()

    def _find_keyboard(self) -> int:
        for index in range(10):
            try:
                if self._context.devices[index].get_HWID():
                    return index
            except OSError:
                continue
        raise DriverNotReadyError("No keyboard was found by the Interception driver")

    @staticmethod
    def foreground_window() -> int:
        return int(user32.GetForegroundWindow()) if IS_WINDOWS else 0

    def assert_focus(self) -> None:
        if self.foreground_window() != self.target_window:
            raise FocusChangedError("Активное окно изменилось, ввод безопасно остановлен")

    def _get_hkl(self) -> int:
        thread_id = user32.GetWindowThreadProcessId(self.target_window, None)
        return int(user32.GetKeyboardLayout(thread_id))

    def _key_data(self, vk: int, hkl: int) -> tuple[int, int]:
        mapped = int(user32.MapVirtualKeyExW(vk, self.MAPVK_VK_TO_VSC_EX, hkl))
        scan = mapped & 0xFF
        flags = int(KeyFlag.KEY_E0) if ((mapped >> 8) & 0xFF) in (0xE0, 0xE1) else 0
        if not scan:
            raise DriverNotReadyError(f"Windows could not map virtual key 0x{vk:02X}")
        return scan, flags

    def _send(self, scan: int, flags: int, key_up: bool = False) -> None:
        state = flags | (int(KeyFlag.KEY_UP) if key_up else int(KeyFlag.KEY_DOWN))
        self._context.send(self._keyboard, KeyStroke(scan, state))

    def _tap_vk(self, vk: int, modifiers: int = 0) -> None:
        self.assert_focus()
        hkl = self._get_hkl()
        modifier_vks: list[int] = []
        if modifiers & 1:
            modifier_vks.append(self.VK_SHIFT)
        if modifiers & 2:
            modifier_vks.append(self.VK_CONTROL)
        if modifiers & 4:
            modifier_vks.append(self.VK_MENU)

        modifier_data = [self._key_data(mod, hkl) for mod in modifier_vks]
        scan, flags = self._key_data(vk, hkl)
        for mod_scan, mod_flags in modifier_data:
            self._send(mod_scan, mod_flags)

        self._send(scan, flags)
        # A real key has measurable hold time, but this time is part of the requested
        # character interval and must not be added on top of the selected WPM.
        time.sleep(self._rng.uniform(0.018, 0.038))
        self._send(scan, flags, key_up=True)

        for mod_scan, mod_flags in reversed(modifier_data):
            self._send(mod_scan, mod_flags, key_up=True)

    def write(self, char: str) -> None:
        if len(char) != 1:
            raise ValueError("write() accepts exactly one character")
        result = int(user32.VkKeyScanExW(char, self._get_hkl()))
        if result == -1:
            raise DriverNotReadyError(
                f"Character {char!r} is unavailable in the active keyboard layout"
            )
        self._tap_vk(result & 0xFF, (result >> 8) & 0xFF)

    def enter(self) -> None:
        self._tap_vk(self.VK_RETURN)

    def backspace(self) -> None:
        self._tap_vk(self.VK_BACK)

    def close(self) -> None:
        self._context.destroy()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
