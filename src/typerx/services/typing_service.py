from __future__ import annotations

import random
import re
import threading
import time
from collections.abc import Callable

import pythoncom
from pywinauto import Desktop

from typerx.domain.models import TypingProfile
from typerx.domain.rhythm import RhythmEngine
from typerx.domain.splitter import SplitPlan
from typerx.domain.typing_physics import finger_for_key
from typerx.domain.typos import TypoKind, TypoPlanner
from typerx.platform.interception_keyboard import InterceptionKeyboard, PressedKey


class TypingCancelled(Exception):
    pass


class ChallengeWatcher:
    _PATTERN = re.compile(r"^123(?:\s+оба)?[.!?]?$", re.IGNORECASE)

    def __init__(self, target_window: int) -> None:
        self.target_window = target_window
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._pending = threading.Event()
        self._seen: set[tuple[object, str]] = set()
        self._suppress_until = 0.0
        self._thread = threading.Thread(target=self._run, name="typerx-123-watch", daemon=True)

    def start(self) -> None:
        self._thread.start()
        self._ready.wait(timeout=1.5)

    def consume(self) -> bool:
        if not self._pending.is_set():
            return False
        self._pending.clear()
        return True

    def suppress_own_reply(self) -> None:
        self._suppress_until = time.monotonic() + 1.5

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)

    def _snapshot(self) -> set[tuple[object, str]]:
        window = Desktop(backend="uia").window(handle=self.target_window)
        result: set[tuple[object, str]] = set()
        for control in window.descendants(control_type="Text"):
            text = control.window_text().strip()
            if text:
                result.add((tuple(control.element_info.runtime_id or ()), text))
        return result

    def _run(self) -> None:
        pythoncom.CoInitialize()
        try:
            try:
                self._seen = self._snapshot()
            finally:
                self._ready.set()
            while not self._stop.wait(0.25):
                try:
                    current = self._snapshot()
                except Exception:
                    continue
                new_items = current - self._seen
                self._seen.update(current)
                if time.monotonic() >= self._suppress_until and any(
                    self._PATTERN.fullmatch(text) for _, text in new_items
                ):
                    self._pending.set()
        finally:
            pythoncom.CoUninitialize()


class TypingService:
    MAX_HELD_KEYS = 3

    def __init__(self, sleep: Callable[[float], None] = time.sleep) -> None:
        self._sleep = sleep
        self._cancel = threading.Event()
        self._pause_requested = threading.Event()
        self._paused = threading.Event()
        self._pause_lock = threading.Lock()

    def cancel(self) -> None:
        self._cancel.set()
        self._pause_requested.clear()
        self._paused.clear()

    def toggle_pause(self) -> str:
        with self._pause_lock:
            if self._paused.is_set() or self._pause_requested.is_set():
                self._pause_requested.clear()
                self._paused.clear()
                return "resumed"
            self._pause_requested.set()
            return "requested"

    def _pause_on_word_boundary(self, at_boundary: bool) -> None:
        if not at_boundary or not self._pause_requested.is_set():
            return
        self._pause_requested.clear()
        self._paused.set()
        while self._paused.is_set():
            if self._cancel.wait(0.05):
                raise TypingCancelled

    def run(
        self,
        plan: SplitPlan,
        profile: TypingProfile,
        target_window: int,
        progress: Callable[[int, int], None],
    ) -> None:
        self._cancel.clear()
        self._pause_requested.clear()
        self._paused.clear()
        output = InterceptionKeyboard(target_window)
        pending: list[tuple[float, PressedKey, str]] = []
        watcher = ChallengeWatcher(target_window) if profile.auto_123_challenge else None
        try:
            if watcher is not None:
                watcher.start()
            rng = random.Random()
            normalized = profile.normalized()
            rhythm = RhythmEngine(normalized, rng)
            typo_planner = TypoPlanner(
                normalized.typo_rate if normalized.fix_typos else 0.0,
                rng,
                correct_typos=normalized.correct_typos,
            )
            total = len(plan.messages)
            previous: str | None = None

            def release_entry(entry: tuple[float, PressedKey, str]) -> None:
                output.release(entry[1])
                pending.remove(entry)

            def wait_until(deadline: float) -> None:
                while pending:
                    entry = min(pending, key=lambda item: item[0])
                    if entry[0] > deadline:
                        break
                    self._wait(max(0.0, entry[0] - time.perf_counter()))
                    release_entry(entry)
                self._wait(max(0.0, deadline - time.perf_counter()))

            def flush_pending() -> None:
                while pending:
                    entry = min(pending, key=lambda item: item[0])
                    self._wait(max(0.0, entry[0] - time.perf_counter()))
                    release_entry(entry)

            def make_physical_room(value: str) -> None:
                now = time.perf_counter()
                for entry in sorted(pending, key=lambda item: item[0]):
                    if entry[0] <= now:
                        release_entry(entry)
                finger = finger_for_key(value)
                conflict = next(
                    (entry for entry in sorted(pending, key=lambda item: item[0]) if entry[2] == finger),
                    None,
                )
                if conflict is not None:
                    wait_until(conflict[0])
                if len(pending) >= self.MAX_HELD_KEYS:
                    wait_until(min(entry[0] for entry in pending))

            def emit(value: str, press: Callable[[], PressedKey]) -> None:
                nonlocal previous
                self._check()
                make_physical_room(value)
                dwell, flight = rhythm.keystroke_timing(value, previous)
                down_at = time.perf_counter()
                key = press()
                pending.append((down_at + dwell, key, finger_for_key(value)))
                wait_until(down_at + max(0.018, dwell + flight))
                previous = value

            def emit_char(value: str) -> None:
                emit(value, lambda: output.press(value))

            def emit_backspace() -> None:
                emit("\b", output.press_backspace)

            def answer_challenge() -> None:
                nonlocal previous
                if watcher is None or not watcher.consume():
                    return
                flush_pending()
                emit("\n", output.press_enter)
                flush_pending()
                self._wait(rng.uniform(0.08, 0.20))
                for digit in "123":
                    emit_char(digit)
                flush_pending()
                emit("\n", output.press_enter)
                flush_pending()
                watcher.suppress_own_reply()
                self._wait(rng.uniform(0.06, 0.16))
                previous = "\n"

            for message_index, message in enumerate(plan.messages, start=1):
                progress(message_index, total)
                typos = typo_planner.plan(message)
                for char_index, char in enumerate(message):
                    answer_challenge()
                    typo = typos.get(char_index)
                    if typo is not None and typo.kind is TypoKind.OMIT:
                        continue
                    if typo is not None:
                        emit_char(typo.replacement)
                        if typo.kind is TypoKind.CORRECTED:
                            flush_pending()
                            before, after = rhythm.correction_pause()
                            self._wait(before)
                            emit_backspace()
                            flush_pending()
                            self._wait(after)
                            emit_char(char)
                    else:
                        emit_char(char)

                    at_boundary = char.isspace() or char_index == len(message) - 1
                    if at_boundary:
                        flush_pending()
                    self._pause_on_word_boundary(at_boundary)

                answer_challenge()
                flush_pending()
                self._pause_on_word_boundary(True)
                self._wait(rhythm.before_send_pause())
                emit("\n", output.press_enter)
                flush_pending()
                previous = "\n"
                if message_index < total:
                    self._wait(rhythm.between_messages_pause(len(message)))
        finally:
            if watcher is not None:
                watcher.close()
            for _, key, _ in pending:
                try:
                    output.release(key)
                except Exception:
                    pass
            output.close()

    def _wait(self, duration: float) -> None:
        if self._cancel.wait(duration):
            raise TypingCancelled

    def _check(self) -> None:
        if self._cancel.is_set():
            raise TypingCancelled
