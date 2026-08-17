from __future__ import annotations

import math
import random
from dataclasses import dataclass

from typerx.domain.models import TypingProfile


@dataclass(slots=True)
class RhythmEngine:
    """Generate correlated dwell and signed flight timings."""

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

        # The event driver, releases, corrections, and message boundaries add
        # real wall-clock cost. Compensate progressively above 180 WPM so the UI
        # value remains the observed throughput instead of only a raw delay hint.
        base_interval = 60.0 / (max(25, self.profile.wpm) * 5.0)
        base_interval *= self._runtime_compensation()
        onset_interval = base_interval * self._phrase
        onset_interval *= math.exp(self._tempo * (0.15 + variation * 0.20))
        onset_interval *= math.exp(self.rng.gauss(0.0, 0.07 + variation * 0.20))

        if char.isspace():
            onset_interval *= self.rng.uniform(0.82, 1.15)
        elif previous and previous.casefold() == char.casefold():
            onset_interval *= self.rng.uniform(1.12, 1.30)

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

        hesitation_rate = 0.025 + variation * 0.05
        if not char.isspace() and self.rng.random() < hesitation_rate:
            onset_interval += self.rng.uniform(0.06, 0.20) * self._speed_factor()

        onset_interval = min(0.95, max(0.018, onset_interval))
        # Faster onset scheduling needs slightly deeper overlap while retaining
        # the calibrated 45-180 ms physical holds.
        flight = min(0.80, max(-0.075, onset_interval - dwell))
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

    def _runtime_compensation(self) -> float:
        high_speed = max(0.0, min(1.0, (self.profile.wpm - 180.0) / 120.0))
        return 1.0 - 0.50 * high_speed

    def _speed_factor(self) -> float:
        return max(0.22, min(1.0, 100.0 / max(25, self.profile.wpm)))
