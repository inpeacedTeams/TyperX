from __future__ import annotations

import ctypes
import random
import time
from ctypes import wintypes
from dataclasses import dataclass

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
    user32.LoadKeyboardLayoutW.argtypes = (wintypes.LPCWSTR, wintypes.UINT)
    user32.LoadKeyboardLayoutW.restype = wintypes.HKL
    user32.PostMessageW.argtypes = (
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )
    user32.PostMessageW.restype = wintypes.BOOL
    user32.VkKeyScanExW.argtypes = (wintypes.WCHAR, wintypes.HKL)
    user32.VkKeyScanExW.restype = ctypes.c_short
    user32.MapVirtualKeyExW.argtypes = (wintypes.UINT, wintypes.UINT, wintypes.HKL)
    user32.MapVirtualKeyExW.restype = wintypes.UINT


class DriverNotReadyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PressedKey:
    scan: int
    flags: int
    modifiers: tuple[tuple[int, int], ...]


class InterceptionKeyboard:
    MAPVK_VK_TO_VSC_EX = 4
    WM_INPUTLANGCHANGEREQUEST = 0x0050
    KLF_ACTIVATE = 0x00000001
    VK_BACK = 0x08
    VK_RETURN = 0x0D
    VK_SHIFT = 0x10
    VK_CONTROL = 0x11
    VK_MENU = 0x12
    RU_LAYOUT = "00000419"
    EN_LAYOUT = "00000409"

    def __init__(self, target_window: int) -> None:
        if not IS_WINDOWS:
            raise UnsupportedPlatformError("TyperX input is available on Windows only")
        self.target_window = target_window
        self._rng = random.Random()
        self._context = Interception()
        self._held_modifiers: dict[tuple[int, int], int] = {}
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

    @staticmethod
    def _layout_for(char: str) -> str | None:
        folded = char.casefold()
        if "а" <= folded <= "я" or folded == "ё":
            return InterceptionKeyboard.RU_LAYOUT
        if "a" <= folded <= "z":
            return InterceptionKeyboard.EN_LAYOUT
        return None

    def _resolve_char(self, char: str) -> tuple[int, int, int]:
        hkl = self._get_hkl()
        result = int(user32.VkKeyScanExW(char, hkl))
        if result != -1:
            return result & 0xFF, (result >> 8) & 0xFF, hkl

        layout_id = self._layout_for(char)
        if layout_id is None:
            raise DriverNotReadyError(
                f"Character {char!r} is unavailable in the active keyboard layout"
            )
        requested_hkl = int(user32.LoadKeyboardLayoutW(layout_id, self.KLF_ACTIVATE))
        if not requested_hkl:
            raise DriverNotReadyError(f"Windows keyboard layout {layout_id} is not installed")

        self.assert_focus()
        user32.PostMessageW(self.target_window, self.WM_INPUTLANGCHANGEREQUEST, 0, requested_hkl)
        for _ in range(10):
            time.sleep(0.01)
            hkl = self._get_hkl()
            result = int(user32.VkKeyScanExW(char, hkl))
            if result != -1:
                return result & 0xFF, (result >> 8) & 0xFF, hkl
        raise DriverNotReadyError(f"Could not switch the target window to layout {layout_id}")

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

    def _press_vk(self, vk: int, modifiers: int = 0, hkl: int | None = None) -> PressedKey:
        self.assert_focus()
        if hkl is None:
            hkl = self._get_hkl()
        modifier_vks: list[int] = []
        if modifiers & 1:
            modifier_vks.append(self.VK_SHIFT)
        if modifiers & 2:
            modifier_vks.append(self.VK_CONTROL)
        if modifiers & 4:
            modifier_vks.append(self.VK_MENU)

        modifier_data = tuple(self._key_data(modifier, hkl) for modifier in modifier_vks)
        for modifier in modifier_data:
            count = self._held_modifiers.get(modifier, 0)
            if count == 0:
                self._send(*modifier)
            self._held_modifiers[modifier] = count + 1

        scan, flags = self._key_data(vk, hkl)
        self._send(scan, flags)
        return PressedKey(scan, flags, modifier_data)

    def release(self, key: PressedKey) -> None:
        self._send(key.scan, key.flags, key_up=True)
        for modifier in reversed(key.modifiers):
            count = self._held_modifiers.get(modifier, 0) - 1
            if count <= 0:
                self._held_modifiers.pop(modifier, None)
                self._send(*modifier, key_up=True)
            else:
                self._held_modifiers[modifier] = count

    def press(self, char: str) -> PressedKey:
        if len(char) != 1:
            raise ValueError("press() accepts exactly one character")
        vk, modifiers, hkl = self._resolve_char(char)
        return self._press_vk(vk, modifiers, hkl)

    def press_enter(self) -> PressedKey:
        return self._press_vk(self.VK_RETURN)

    def press_backspace(self) -> PressedKey:
        return self._press_vk(self.VK_BACK)

    def _tap(self, key: PressedKey, hold_seconds: float | None = None) -> None:
        hold = self._rng.uniform(0.065, 0.105) if hold_seconds is None else hold_seconds
        time.sleep(min(0.25, max(0.025, hold)))
        self.release(key)

    def write(self, char: str, hold_seconds: float | None = None) -> None:
        self._tap(self.press(char), hold_seconds)

    def enter(self, hold_seconds: float | None = None) -> None:
        self._tap(self.press_enter(), hold_seconds)

    def backspace(self, hold_seconds: float | None = None) -> None:
        self._tap(self.press_backspace(), hold_seconds)

    def close(self) -> None:
        self._context.destroy()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
