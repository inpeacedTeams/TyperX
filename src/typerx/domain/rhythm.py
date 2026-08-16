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
        return min(0.95, max(0.008, base * multiplier))

    def correction_pause(self) -> tuple[float, float]:
        speed = self._speed_factor()
        return (
            self.rng.uniform(0.035, 0.11) * speed,
            self.rng.uniform(0.03, 0.09) * speed,
        )

    def before_send_pause(self) -> float:
        # At maximum speed Enter should feel like another keystroke, not a thought pause.
        speed = self._speed_factor()
        return max(0.004, self.rng.uniform(0.012, 0.045) * speed)

    def between_messages_pause(self, previous_length: int) -> float:
        del previous_length
        speed = self._speed_factor()
        return max(0.006, self.rng.uniform(0.018, 0.065) * speed)

    def _speed_factor(self) -> float:
        # 100 WPM keeps a tiny human gap; 280 WPM compresses it to almost zero.
        return max(0.22, min(1.0, 100.0 / max(25, self.profile.wpm)))
