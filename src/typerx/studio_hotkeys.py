"""Desktop hotkeys independent of RegisterHotKey conflicts and the Qt event queue."""
from __future__ import annotations

import ctypes
import threading


class KeyEdges:
    def __init__(self, start=False, stop=False):
        self.start, self.stop = start, stop

    def update(self, start, stop):
        action = "stop" if stop and not self.stop else "start" if start and not self.start and not stop else None
        self.start, self.stop = start, stop
        return action


class GlobalHotkeys:
    def __init__(self, on_start, on_stop, on_error=None):
        self.on_start, self.on_stop = on_start, on_stop
        self.on_error = on_error or (lambda message: None)
        self._thread = None
        self._closed = threading.Event()

    def start(self):
        if self._thread is not None:
            return
        if not hasattr(ctypes, "WinDLL"):
            raise OSError("Глобальные F8/F9 поддерживаются только в Windows")
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._key = user32.GetAsyncKeyState
        self._key.argtypes = [ctypes.c_int]
        self._key.restype = ctypes.c_short
        self._closed.clear()
        self._thread = threading.Thread(target=self._run, name="typerx-studio-keys", daemon=True)
        self._thread.start()

    def _pressed(self, key):
        # The low 'pressed since last call' bit is shared with other processes; do not use it.
        return bool(self._key(key) & 0x8000)

    def _run(self):
        try:
            edges = KeyEdges(self._pressed(0x77), self._pressed(0x78))
            while not self._closed.wait(0.015):
                action = edges.update(self._pressed(0x77), self._pressed(0x78))
                if action == "stop":
                    self.on_stop()  # F9 never waits for Qt or the LLM request lock.
                elif action == "start":
                    self.on_start()
        except Exception:
            self.on_stop()
            self.on_error("Обработчик F8/F9 остановлен. Перезапусти TyperX; запуск отключён до перезапуска.")

    def close(self):
        self._closed.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)
