from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass

from typerx.domain.models import TypingProfile
from typerx.domain.typos import Typo

SAFE_RAW_WPM = 340


def scored_character_count(text: str, typos: dict[int, Typo], correct_typos: bool) -> int:
    """Estimate Monkeytype's correctWord character count for the final input."""
    if correct_typos or not typos:
        return len(text)
    scored = 0
    word_start: int | None = None
    for index, char in enumerate(text + " "):
        if not char.isspace() and word_start is None:
            word_start = index
        if not char.isspace() or word_start is None:
            continue
        word_end = index
        word_is_correct = not any(word_start <= typo_index < word_end for typo_index in typos)
        if word_is_correct:
            scored += word_end - word_start
            if index < len(text):
                scored += 1
        word_start = None
    return max(1, scored)


def _word_penalties(text: str, typos: dict[int, Typo]) -> dict[int, int]:
    penalties: dict[int, int] = {}
    word_start: int | None = None
    for index, char in enumerate(text + " "):
        if not char.isspace() and word_start is None:
            word_start = index
        if not char.isspace() or word_start is None:
            continue
        typo_indexes = [position for position in typos if word_start <= position < index]
        if typo_indexes:
            penalty = index - word_start + (1 if index < len(text) else 0)
            for position in typo_indexes:
                penalties[position] = penalty
        word_start = None
    return penalties


def fit_typos_to_raw_limit(text: str, target_wpm: int, typos: dict[int, Typo], correct_typos: bool, raw_limit: int = SAFE_RAW_WPM) -> dict[int, Typo]:
    """Keep as many errors as possible without making Monkeytype reject raw WPM."""
    if correct_typos or not typos or target_wpm >= raw_limit:
        return {} if not correct_typos and target_wpm >= raw_limit else dict(typos)
    kept = dict(typos)
    required_scored = math.ceil(len(text) * target_wpm / raw_limit)
    penalties = _word_penalties(text, kept)
    for index in sorted(kept, key=lambda item: penalties.get(item, 0), reverse=True):
        if scored_character_count(text, kept, False) >= required_scored:
            break
        kept.pop(index)
    return kept


def emitted_event_count(text: str, typos: dict[int, Typo], correct_typos: bool) -> int:
    return max(1, len(text) + (2 * len(typos) if correct_typos else 0))


def event_interval_seconds(text: str, target_wpm: int, typos: dict[int, Typo], correct_typos: bool) -> float:
    scored = scored_character_count(text, typos, correct_typos)
    duration = scored / (max(25, target_wpm) * 5.0) * 60.0
    return max(0.010, duration / emitted_event_count(text, typos, correct_typos))


@dataclass(slots=True)
class AdaptiveDeadlinePacer:
    """Monkeytype-only pacer with safe cumulative, text-aware intervals."""

    started_at: float
    base_interval: float
    text_length: int
    profile: TypingProfile
    rng: random.Random
    events: int = 0
    _tempo: float = 0.0
    _last_word_length: int = 0
    _deadline: float | None = None

    def next_deadline(self, char: str, previous: str | None, position: int) -> float:
        self.events += 1
        variation = self.profile.variation / 100.0
        self._tempo = 0.82 * self._tempo + self.rng.gauss(0.0, 0.22 + variation * 0.30)
        progress = position / max(1, self.text_length - 1)
        fatigue = 1.0 + (0.025 + variation * 0.10) * progress * progress
        interval = self.base_interval * math.exp(self._tempo * (0.16 + variation * 0.10))
        interval *= math.exp(self.rng.gauss(0.0, 0.035 + variation * 0.055))

        if char.isspace():
            interval *= self.rng.uniform(0.86, 1.12)
        elif previous and previous.casefold() == char.casefold():
            interval *= self.rng.uniform(1.08, 1.22)
        if char in ",:;":
            interval += self.base_interval * self.rng.uniform(0.7, 1.6)
        elif char in ".!?…":
            interval += self.base_interval * self.rng.uniform(1.8, 3.8)
        if self._last_word_length >= 8 and char.isspace():
            interval += self.base_interval * self.rng.uniform(0.4, 1.0)
        if not char.isspace() and self.rng.random() < 0.018 + variation * 0.045:
            interval += self.rng.uniform(0.035, 0.14)
        if char.isspace():
            self._last_word_length = 0
        else:
            self._last_word_length += 1

        interval = max(0.010, min(0.95, interval * fatigue))
        previous_deadline = self.started_at if self._deadline is None else self._deadline
        self._deadline = max(previous_deadline, time.perf_counter()) + interval
        return self._deadline


@dataclass(slots=True)
class DeadlinePacer:
    started_at: float
    interval: float
    events: int = 0

    def next_deadline(self) -> float:
        self.events += 1
        return self.started_at + self.events * self.interval
