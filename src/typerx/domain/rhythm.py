from __future__ import annotations

import math
import random
from dataclasses import dataclass

from typerx.domain.models import TypingProfile


@dataclass(slots=True)
class RhythmEngine:
    """Generate correlated dwell and signed flight timings.

    Dwell is keydown -> keyup. Flight is keyup -> next keydown and may be
    negative, which represents the overlap visible in real key timelines.
    """

    profile: TypingProfile
    rng: random.Random
    _tempo: float = 0.0
    _touch: float = 0.0
    _phrase: float = 1.0
    _phrase_left: int = 0

    def keystroke_timing(self, char: str, previous: str | None = None) -> tuple[float, float]:
        if self._phrase_left <= 0:
            self._phrase = self.rng.uniform(0.70, 1.45)
            self._phrase_left = self.rng.randint(4, 15)
        self._phrase_left -= 1

        variation = self.profile.variation / 100.0
        self._tempo = 0.84 * self._tempo + self.rng.gauss(0.0, 0.34 + variation * 0.55)
        self._touch = (
            0.70 * self._touch
            + 0.16 * self._tempo
            + self.rng.gauss(0.0, 0.38 + variation * 0.25)
        )

        # Phrase-level drift, correlated tempo, and moderate per-key variation
        # reproduce arrhythmia without either a metronome or white-noise timing.
        base_interval = 60.0 / (max(25, self.profile.wpm) * 5.0)
        onset_interval = base_interval * self._phrase
        onset_interval *= math.exp(self._tempo * (0.15 + variation * 0.20))
        onset_interval *= math.exp(self.rng.gauss(0.0, 0.07 + variation * 0.20))

        if char.isspace():
            onset_interval *= self.rng.uniform(0.82, 1.15)
        elif previous and previous.casefold() == char.casefold():
            onset_interval *= self.rng.uniform(1.12, 1.30)

        # Calibrated from the supplied live sample: most holds are 50-115 ms,
        # with a thinner tail toward 170 ms.
        dwell = 0.086 * math.exp(self._touch * (0.10 + variation * 0.08))
        dwell *= math.exp(self.rng.gauss(0.0, 0.11 + variation * 0.10))
        if char.isspace():
            dwell *= self.rng.uniform(0.82, 0.98)
        elif char in "\b\n":
            dwell *= self.rng.uniform(1.00, 1.20)
        dwell = min(0.180, max(0.045, dwell))

        if self.profile.punctuation_pauses and char in ",:;":
            onset_interval += base_interval * self.rng.uniform(0.8, 1.8)
        elif self.profile.punctuation_pauses and char in ".!?…":
            onset_interval += base_interval * self.rng.uniform(2.0, 4.2)

        # A small right tail of thought/coordination pauses is present in the
        # sample and keeps the overlap ratio from becoming mechanically uniform.
        hesitation_rate = 0.025 + variation * 0.05
        if not char.isspace() and self.rng.random() < hesitation_rate:
            onset_interval += self.rng.uniform(0.06, 0.20) * self._speed_factor()

        onset_interval = min(0.95, max(0.018, onset_interval))
        flight = min(0.80, max(-0.060, onset_interval - dwell))
        return dwell, flight

    def character_delay(self, char: str) -> float:
        dwell, flight = self.keystroke_timing(char)
        return min(0.95, max(0.008, dwell + flight))

    def correction_pause(self) -> tuple[float, float]:
        speed = self._speed_factor()
        return (
            self.rng.uniform(0.055, 0.16) * speed,
            self.rng.uniform(0.045, 0.13) * speed,
        )

    def before_send_pause(self) -> float:
        speed = self._speed_factor()
        return max(0.006, self.rng.uniform(0.018, 0.065) * speed)

    def between_messages_pause(self, previous_length: int) -> float:
        length_factor = min(1.5, max(0.8, previous_length / 40.0))
        speed = self._speed_factor()
        return max(0.010, self.rng.uniform(0.035, 0.12) * speed * length_factor)

    def _speed_factor(self) -> float:
        return max(0.22, min(1.0, 100.0 / max(25, self.profile.wpm)))
