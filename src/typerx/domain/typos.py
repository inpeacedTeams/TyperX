from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum, auto

_NEIGHBOURS = {
    "а": "пвм", "б": "юьл", "в": "аып", "г": "ншр", "д": "лж", "е": "кн", "ё": "1й",
    "ж": "дэ", "з": "хщ", "и": "мть", "й": "цф", "к": "уен", "л": "джо", "м": "сиа",
    "н": "геп", "о": "лр", "п": "арн", "р": "от", "с": "мч", "т": "ьи", "у": "кц",
    "ф": "йы", "х": "зъ", "ц": "уй", "ч": "ся", "ш": "щг", "щ": "шз", "ъ": "х",
    "ы": "вф", "ь": "тб", "э": "ж", "ю": "б", "я": "чс",
    "q": "wa", "w": "qase", "e": "wsdr", "r": "edft", "t": "rfgy", "y": "tghu",
    "u": "yhji", "i": "ujko", "o": "iklp", "p": "ol", "a": "qwsz", "s": "awedxz",
    "d": "serfcx", "f": "drtgvc", "g": "ftyhbv", "h": "gyujnb", "j": "huikmn",
    "k": "jiolm", "l": "kop", "z": "asx", "x": "zsdc", "c": "xdfv", "v": "cfgb",
    "b": "vghn", "n": "bhjm", "m": "njk",
}


class TypoKind(Enum):
    OMIT = auto()
    SUBSTITUTE = auto()
    CORRECTED = auto()


@dataclass(frozen=True, slots=True)
class Typo:
    index: int
    kind: TypoKind
    replacement: str = ""


class TypoPlanner:
    def __init__(
        self,
        rate: float,
        rng: random.Random,
        correct_typos: bool = True,
        corrections_only: bool = False,
    ) -> None:
        self.rate = max(0.0, min(40.0, rate)) / 100.0
        self.rng = rng
        self.correct_typos = correct_typos
        self.corrections_only = corrections_only

    def plan(self, text: str) -> dict[int, Typo]:
        actions: dict[int, Typo] = {}
        word_start: int | None = None
        for index, char in enumerate(text + " "):
            if char.isalpha() and word_start is None:
                word_start = index
            if char.isalpha() or word_start is None:
                continue
            self._plan_word(text, word_start, index, actions)
            word_start = None
        return actions

    def _plan_word(self, text: str, start: int, end: int, actions: dict[int, Typo]) -> None:
        length = end - start
        if length < 3 or self.rng.random() >= self.rate:
            return
        candidates = [
            index
            for index in range(start + 1, end - 1 if length >= 5 else end)
            if text[index].casefold() in _NEIGHBOURS
        ]
        if not candidates:
            return
        index = self.rng.choice(candidates)
        original = text[index]
        replacement = self.rng.choice(_NEIGHBOURS[original.casefold()])
        if original.isupper():
            replacement = replacement.upper()
        if self.corrections_only:
            actions[index] = Typo(index, TypoKind.CORRECTED, replacement)
            return
        roll = self.rng.random()
        if length >= 4 and roll < 0.38:
            actions[index] = Typo(index, TypoKind.OMIT)
            return
        kind = TypoKind.CORRECTED if self.correct_typos and roll >= 0.82 else TypoKind.SUBSTITUTE
        actions[index] = Typo(index, kind, replacement)
