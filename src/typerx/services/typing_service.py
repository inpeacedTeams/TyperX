from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable

from typerx.domain.models import TypingProfile
from typerx.domain.rhythm import RhythmEngine
from typerx.domain.splitter import SplitPlan
from typerx.domain.typos import TypoKind, TypoPlanner
from typerx.platform.interception_keyboard import InterceptionKeyboard


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

            def emit_char(value: str) -> None:
                nonlocal previous
                self._check()
                dwell, flight = rhythm.keystroke_timing(value, previous)
                output.write(value, dwell)
                self._wait(flight)
                previous = value

            def emit_backspace() -> None:
                nonlocal previous
                self._check()
                dwell, flight = rhythm.keystroke_timing("\b", previous)
                output.backspace(dwell)
                self._wait(flight)
                previous = "\b"

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
                            before, after = rhythm.correction_pause()
                            self._wait(before)
                            emit_backspace()
                            self._wait(after)
                            emit_char(char)
                    else:
                        emit_char(char)

                self._wait(rhythm.before_send_pause())
                dwell, flight = rhythm.keystroke_timing("\n", previous)
                output.enter(dwell)
                self._wait(flight)
                previous = "\n"
                if message_index < total:
                    self._wait(rhythm.between_messages_pause(len(message)))
        finally:
            output.close()

    def _wait(self, duration: float) -> None:
        if self._cancel.wait(duration):
            raise TypingCancelled

    def _check(self) -> None:
        if self._cancel.is_set():
            raise TypingCancelled
