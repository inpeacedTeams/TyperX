from __future__ import annotations

import math
from dataclasses import dataclass

from typerx.domain.typos import Typo

SAFE_RAW_WPM = 340


def scored_character_count(
    text: str,
    typos: dict[int, Typo],
    correct_typos: bool,
) -> int:
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


def fit_typos_to_raw_limit(
    text: str,
    target_wpm: int,
    typos: dict[int, Typo],
    correct_typos: bool,
    raw_limit: int = SAFE_RAW_WPM,
) -> dict[int, Typo]:
    """Keep as many errors as possible without making Monkeytype reject raw WPM."""
    if correct_typos or not typos or target_wpm >= raw_limit:
        return {} if not correct_typos and target_wpm >= raw_limit else dict(typos)

    kept = dict(typos)
    required_scored = math.ceil(len(text) * target_wpm / raw_limit)
    penalties = _word_penalties(text, kept)
    # Recover the most scored characters per removed error first. This leaves
    # the largest possible number of visible mistakes under Monkeytype's cap.
    for index in sorted(kept, key=lambda item: penalties.get(item, 0), reverse=True):
        if scored_character_count(text, kept, False) >= required_scored:
            break
        kept.pop(index)
    return kept


def emitted_event_count(
    text: str,
    typos: dict[int, Typo],
    correct_typos: bool,
) -> int:
    return max(1, len(text) + (2 * len(typos) if correct_typos else 0))


def event_interval_seconds(
    text: str,
    target_wpm: int,
    typos: dict[int, Typo],
    correct_typos: bool,
) -> float:
    scored = scored_character_count(text, typos, correct_typos)
    duration = scored / (max(25, target_wpm) * 5.0) * 60.0
    return max(0.010, duration / emitted_event_count(text, typos, correct_typos))


@dataclass(slots=True)
class DeadlinePacer:
    started_at: float
    interval: float
    events: int = 0

    def next_deadline(self) -> float:
        self.events += 1
        return self.started_at + self.events * self.interval
