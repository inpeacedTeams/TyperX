from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable

from typerx.domain.models import TypingProfile
from typerx.domain.rhythm import RhythmEngine
from typerx.domain.splitter import SplitPlan
from typerx.platform.windows import WindowsInput

_NEIGHBOURS = {
    "а": "пвм", "б": "юьл", "в": "аып", "г": "ншр", "д": "лж", "е": "кн", "ё": "1й",
    "ж": "дэ", "з": "хщ", "и": "мть", "й": "цф", "к": "уен", "л": "джо", "м": "сиа",
    "н": "геп", "о": "лр", "п": "арн", "р": "от", "с": "мч", "т": "ьи", "у": "кц",
    "ф": "йы", "х": "зъ", "ц": "уй", "ч": "ся", "ш": "щг", "щ": "шз", "ъ": "х",
    "ы": "вф", "ь": "тб", "э": "ж", "ю": "б", "я": "чс",
}


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
        output = WindowsInput(target_window)
        rng = random.Random()
        rhythm = RhythmEngine(profile.normalized(), rng)
        total = len(plan.messages)
        for index, message in enumerate(plan.messages, start=1):
            progress(index, total)
            for char in message:
                self._check()
                if rhythm.should_typo(char) and char.casefold() in _NEIGHBOURS:
                    wrong = rng.choice(_NEIGHBOURS[char.casefold()])
                    output.write(wrong.upper() if char.isupper() else wrong)
                    before, after = rhythm.correction_pause()
                    self._wait(before)
                    output.backspace()
                    self._wait(after)
                output.write(char)
                self._wait(rhythm.character_delay(char))
            self._wait(rhythm.before_send_pause())
            output.enter()
            if index < total:
                self._wait(rhythm.between_messages_pause(len(message)))

    def _wait(self, duration: float) -> None:
        if self._cancel.wait(duration):
            raise TypingCancelled

    def _check(self) -> None:
        if self._cancel.is_set():
            raise TypingCancelled
