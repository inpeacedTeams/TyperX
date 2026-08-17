from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

IS_WINDOWS = hasattr(ctypes, "WinDLL")
WDA_EXCLUDEFROMCAPTURE = 0x00000011

if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.EnumWindows.argtypes = (ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM)
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.SetWindowDisplayAffinity.argtypes = (wintypes.HWND, wintypes.DWORD)
    user32.SetWindowDisplayAffinity.restype = wintypes.BOOL


def exclude_process_windows_from_capture() -> int:
    """Apply WDA_EXCLUDEFROMCAPTURE to every top-level window owned by TyperX.

    Re-running is intentional: Qt may create native handles later for dialogs, menus,
    error boxes and restored windows.
    """
    if not IS_WINDOWS:
        return 0

    current_pid = os.getpid()
    protected = 0
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def callback(hwnd: int, _lparam: int) -> bool:
        nonlocal protected
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == current_pid:
            if user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE):
                protected += 1
        return True

    user32.EnumWindows(callback, 0)
    return protected
