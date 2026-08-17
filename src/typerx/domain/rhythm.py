from __future__ import annotations

import math
import random
from dataclasses import dataclass

from typerx.domain.models import TypingProfile


@dataclass(slots=True)
class RhythmEngine:
    """Generate a continuous typing rhythm instead of independent random delays.

    The two returned values are key dwell time (keydown -> keyup) and flight time
    (keyup -> next keydown). Both share latent state, so tempo changes persist for
    several keystrokes instead of producing white-noise timing.
    """

    profile: TypingProfile
    rng: random.Random
    _tempo: float = 0.0
    _touch: float = 0.0
    _burst: float = 1.0
    _burst_left: int = 0

    def keystroke_timing(self, char: str, previous: str | None = None) -> tuple[float, float]:
        if self._burst_left <= 0:
            self._burst = self.rng.uniform(0.86, 1.16)
            self._burst_left = self.rng.randint(5, 17)
        self._burst_left -= 1

        variation = self.profile.variation / 100.0
        # Slowly moving latent states create the short-range autocorrelation seen
        # in real typing. Touch partly follows tempo, linking dwell and flight.
        self._tempo = 0.86 * self._tempo + self.rng.gauss(0.0, 0.42 + variation)
        self._touch = 0.72 * self._touch + 0.20 * self._tempo + self.rng.gauss(0.0, 0.34)

        base = 60.0 / (max(25, self.profile.wpm) * 5.0)
        interval = base * self._burst * math.exp(self._tempo * (0.10 + variation * 0.22))

        if char.isspace():
            interval *= 0.76
        elif previous and previous.casefold() == char.casefold():
            interval *= 1.12

        dwell_share = 0.34 * math.exp(self._touch * (0.08 + variation * 0.10))
        dwell = interval * dwell_share
        if char.isspace():
            dwell *= 0.82
        dwell = min(0.180, max(0.022, dwell))

        flight = max(0.004, interval - dwell)
        if self.profile.punctuation_pauses and char in ",:;":
            flight += base * self.rng.uniform(0.8, 1.8)
        elif self.profile.punctuation_pauses and char in ".!?…":
            flight += base * self.rng.uniform(2.2, 4.5)
        return dwell, min(0.95, flight)

    def character_delay(self, char: str) -> float:
        dwell, flight = self.keystroke_timing(char)
        return min(0.95, max(0.008, dwell + flight))

    def correction_pause(self) -> tuple[float, float]:
        speed = self._speed_factor()
        return (
            self.rng.uniform(0.035, 0.11) * speed,
            self.rng.uniform(0.03, 0.09) * speed,
        )

    def before_send_pause(self) -> float:
        speed = self._speed_factor()
        return max(0.004, self.rng.uniform(0.012, 0.045) * speed)

    def between_messages_pause(self, previous_length: int) -> float:
        del previous_length
        speed = self._speed_factor()
        return max(0.006, self.rng.uniform(0.018, 0.065) * speed)

    def _speed_factor(self) -> float:
        return max(0.22, min(1.0, 100.0 / max(25, self.profile.wpm)))
