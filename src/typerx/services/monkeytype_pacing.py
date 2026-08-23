from __future__ import annotations

from dataclasses import dataclass

from typerx.domain.typos import Typo


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


def emitted_event_count(
    text: str,
    typos: dict[int, Typo],
    correct_typos: bool,
) -> int:
    # A corrected typo adds a wrong key and Backspace before the original key.
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
