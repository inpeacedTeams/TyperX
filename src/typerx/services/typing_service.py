from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable

from typerx.domain.models import TypingProfile
from typerx.domain.rhythm import RhythmEngine
from typerx.domain.splitter import SplitPlan
from typerx.domain.typos import TypoKind, TypoPlanner
from typerx.platform.interception_keyboard import InterceptionKeyboard, PressedKey


class TypingCancelled(Exception):
    pass


class TypingService:
    def __init__(self, sleep: Callable[[float], None] = time.sleep) -> None:
        self._sleep = sleep
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(
        self,
        plan: SplitPlan,
        profile: TypingProfile,
        target_window: int,
        progress: Callable[[int, int], None],
    ) -> None:
        self._cancel.clear()
        output = InterceptionKeyboard(target_window)
        pending: list[tuple[float, PressedKey]] = []
        try:
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

            def wait_until(deadline: float) -> None:
                while pending:
                    release_at, key = min(pending, key=lambda item: item[0])
                    if release_at > deadline:
                        break
                    self._wait(max(0.0, release_at - time.perf_counter()))
                    output.release(key)
                    pending.remove((release_at, key))
                self._wait(max(0.0, deadline - time.perf_counter()))

            def flush_pending() -> None:
                while pending:
                    release_at, key = min(pending, key=lambda item: item[0])
                    self._wait(max(0.0, release_at - time.perf_counter()))
                    output.release(key)
                    pending.remove((release_at, key))

            def emit(value: str, press: Callable[[], PressedKey]) -> None:
                nonlocal previous
                self._check()
                dwell, flight = rhythm.keystroke_timing(value, previous)
                down_at = time.perf_counter()
                key = press()
                pending.append((down_at + dwell, key))
                wait_until(down_at + max(0.018, dwell + flight))
                previous = value

            def emit_char(value: str) -> None:
                emit(value, lambda: output.press(value))

            def emit_backspace() -> None:
                emit("\b", output.press_backspace)

            for message_index, message in enumerate(plan.messages, start=1):
                progress(message_index, total)
                typos = typo_planner.plan(message)
                for char_index, char in enumerate(message):
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

                flush_pending()
                self._wait(rhythm.before_send_pause())
                emit("\n", output.press_enter)
                flush_pending()
                previous = "\n"
                if message_index < total:
                    self._wait(rhythm.between_messages_pause(len(message)))
        finally:
            for _, key in pending:
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
