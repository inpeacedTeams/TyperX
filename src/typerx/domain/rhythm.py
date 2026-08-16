from __future__ import annotations

import random
from dataclasses import dataclass

from typerx.domain.models import TypingProfile


@dataclass(slots=True)
class RhythmEngine:
    profile: TypingProfile
    rng: random.Random
    _burst: float = 1.0
    _burst_left: int = 0

    def character_delay(self, char: str) -> float:
        if self._burst_left <= 0:
            self._burst = self.rng.uniform(0.78, 1.22)
            self._burst_left = self.rng.randint(4, 14)
        self._burst_left -= 1

        base = 60.0 / (max(25, self.profile.wpm) * 5.0)
        sigma = max(0.01, self.profile.variation / 100.0)
        noise = self.rng.lognormvariate(-sigma * sigma / 2, sigma)
        multiplier = self._burst * noise
        if char.isspace():
            multiplier *= 0.62
        elif self.profile.punctuation_pauses and char in ",:;":
            multiplier += self.rng.uniform(1.1, 2.3)
        elif self.profile.punctuation_pauses and char in ".!?…":
            multiplier += self.rng.uniform(2.8, 5.2)
        return min(0.95, max(0.012, base * multiplier))

    def correction_pause(self) -> tuple[float, float]:
        return self.rng.uniform(0.06, 0.17), self.rng.uniform(0.05, 0.14)

    def before_send_pause(self) -> float:
        return self.rng.uniform(0.08, 0.24)

    def between_messages_pause(self, previous_length: int) -> float:
        length_bonus = min(0.16, previous_length * 0.0025)
        return self.rng.uniform(0.16, 0.46) + length_bonus * self.rng.random()
