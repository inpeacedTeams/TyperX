from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable

from typerx.domain.models import TypingProfile
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
            typo_planner = TypoPlanner(
                normalized.typo_rate if normalized.fix_typos else 0.0, rng
            )
            total = len(plan.messages)

            # TypeStats uses the standard conversion: 1 word = 5 characters.
            # Absolute deadlines prevent driver key-hold time, scheduler latency and
            # accumulated sleep error from lowering the measured WPM.
            interval = 60.0 / (normalized.wpm * 5.0)
            next_deadline = time.perf_counter()
            emitted = 0

            def emit(action) -> None:
                nonlocal next_deadline, emitted
                self._check()
                action()
                emitted += 1
                next_deadline += interval
                remaining = next_deadline - time.perf_counter()
                if remaining > 0:
                    self._wait(remaining)
                elif remaining < -interval * 3:
                    # Do not generate a catch-up burst after an OS stall.
                    next_deadline = time.perf_counter()

            for message_index, message in enumerate(plan.messages, start=1):
                progress(message_index, total)
                typos = typo_planner.plan(message)

                for char_index, char in enumerate(message):
                    typo = typos.get(char_index)
                    if typo is not None and typo.kind is TypoKind.OMIT:
                        continue

                    if typo is not None:
                        emit(lambda value=typo.replacement: output.write(value))
                        if typo.kind is TypoKind.CORRECTED:
                            emit(output.backspace)
                            emit(lambda value=char: output.write(value))
                    else:
                        emit(lambda value=char: output.write(value))

                # Enter is a real key event and participates in the same measured cadence.
                emit(output.enter)

            # Keep the variable referenced for diagnostics/profiling without changing pace.
            del emitted
        finally:
            output.close()

    def _wait(self, duration: float) -> None:
        if self._cancel.wait(duration):
            raise TypingCancelled

    def _check(self) -> None:
        if self._cancel.is_set():
            raise TypingCancelled
