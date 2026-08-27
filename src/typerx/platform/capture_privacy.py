from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

IS_WINDOWS = hasattr(ctypes, "WinDLL")
WDA_EXCLUDEFROMCAPTURE = 0x00000011

if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    ENUM_WINDOWS_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = (ENUM_WINDOWS_PROC, wintypes.LPARAM)
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = (
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    )
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.SetWindowDisplayAffinity.argtypes = (wintypes.HWND, wintypes.DWORD)
    user32.SetWindowDisplayAffinity.restype = wintypes.BOOL


def exclude_process_windows_from_capture() -> int:
    """Best-effort capture exclusion that can never break the typing worker."""
    if not IS_WINDOWS:
        return 0

    current_pid = os.getpid()
    protected = 0

    @ENUM_WINDOWS_PROC
    def callback(hwnd: int, _lparam: int) -> bool:
        nonlocal protected
        try:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == current_pid and user32.SetWindowDisplayAffinity(
                hwnd, WDA_EXCLUDEFROMCAPTURE
            ):
                protected += 1
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(callback, 0)
    except Exception:
        return protected
    return protected
