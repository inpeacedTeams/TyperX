import random

from typerx.domain.models import TypingProfile
from typerx.domain.rhythm import RhythmEngine


def test_delays_are_bounded() -> None:
    rhythm = RhythmEngine(TypingProfile(wpm=280, variation=55), random.Random(1))
    values = [rhythm.character_delay("а") for _ in range(1000)]
    assert min(values) >= 0.008
    assert max(values) <= 0.95


def test_punctuation_is_slower_than_letters() -> None:
    letter = RhythmEngine(TypingProfile(), random.Random(4)).character_delay("а")
    mark = RhythmEngine(TypingProfile(), random.Random(4)).character_delay(".")
    assert mark > letter


def test_dwell_and_flight_are_both_variable() -> None:
    rhythm = RhythmEngine(TypingProfile(variation=30), random.Random(7))
    samples = [rhythm.keystroke_timing("а") for _ in range(200)]
    dwells = {round(dwell, 5) for dwell, _ in samples}
    flights = {round(flight, 5) for _, flight in samples}
    assert len(dwells) > 20
    assert len(flights) > 20
    assert all(0.022 <= dwell <= 0.180 for dwell, _ in samples)
    assert all(0.004 <= flight <= 0.95 for _, flight in samples)


def test_tempo_has_short_range_autocorrelation() -> None:
    rhythm = RhythmEngine(TypingProfile(variation=35), random.Random(11))
    values = [sum(rhythm.keystroke_timing("а")) for _ in range(500)]
    mean = sum(values) / len(values)
    numerator = sum(
        (a - mean) * (b - mean) for a, b in zip(values, values[1:], strict=False)
    )
    denominator = sum((value - mean) ** 2 for value in values)
    assert numerator / denominator > 0.15


def test_enter_delay_is_nearly_zero_at_max_speed() -> None:
    rhythm = RhythmEngine(TypingProfile(wpm=280), random.Random(9))
    before = [rhythm.before_send_pause() for _ in range(100)]
    after = [rhythm.between_messages_pause(100) for _ in range(100)]
    assert max(before) < 0.017
    assert max(after) < 0.025


def test_slower_profiles_keep_a_small_gap() -> None:
    rhythm = RhythmEngine(TypingProfile(wpm=80), random.Random(3))
    assert rhythm.between_messages_pause(20) >= 0.018


def test_profile_clamps_untrusted_values() -> None:
    profile = TypingProfile(wpm=9999, variation=-2, typo_rate=100).normalized()
    assert (profile.wpm, profile.variation, profile.typo_rate) == (300, 0, 40.0)
