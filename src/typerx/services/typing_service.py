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
                normalized.typo_rate if normalized.fix_typos else 0.0, rng
            )
            total = len(plan.messages)

            for message_index, message in enumerate(plan.messages, start=1):
                progress(message_index, total)
                typos = typo_planner.plan(message)
                for char_index, char in enumerate(message):
                    self._check()
                    target_interval = rhythm.character_delay(char)
                    cycle_started = time.perf_counter()
                    typo = typos.get(char_index)

                    if typo is not None and typo.kind is TypoKind.OMIT:
                        self._wait(target_interval * 0.55)
                        continue

                    if typo is not None:
                        output.write(typo.replacement)
                        if typo.kind is TypoKind.CORRECTED:
                            before, after = rhythm.correction_pause()
                            self._wait(before)
                            output.backspace()
                            self._wait(after)
                            output.write(char)
                    else:
                        output.write(char)

                    # Driver key-down/key-up time is already elapsed. Subtract it instead
                    # of adding a second delay, so selected WPM equals observed chat WPM.
                    elapsed = time.perf_counter() - cycle_started
                    self._wait(max(0.0, target_interval - elapsed))

                self._wait(rhythm.before_send_pause())
                output.enter()
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
