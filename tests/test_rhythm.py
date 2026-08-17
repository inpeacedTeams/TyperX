import random
from itertools import pairwise
from statistics import median, pstdev

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


def test_dwell_matches_realistic_keyboard_range() -> None:
    rhythm = RhythmEngine(TypingProfile(wpm=240, variation=30), random.Random(7))
    samples = [rhythm.keystroke_timing("а") for _ in range(500)]
    dwells = [dwell for dwell, _ in samples]
    assert min(dwells) >= 0.045
    assert max(dwells) <= 0.180
    assert 0.070 <= median(dwells) <= 0.105
    assert len({round(dwell, 4) for dwell in dwells}) > 50


def test_high_speed_typing_contains_varied_overlap() -> None:
    rhythm = RhythmEngine(TypingProfile(wpm=240, variation=30), random.Random(12))
    flights = [rhythm.keystroke_timing("а")[1] for _ in range(700)]
    negative_share = sum(flight < 0 for flight in flights) / len(flights)
    assert 0.55 <= negative_share <= 1.0
    assert min(flights) >= -0.075
    assert max(flights) > 0.020


def test_300_wpm_compensates_for_runtime_overhead() -> None:
    rhythm = RhythmEngine(TypingProfile(wpm=300, variation=30), random.Random(21))
    intervals = [sum(rhythm.keystroke_timing("а")) for _ in range(3000)]
    internal_wpm = 60.0 / (5.0 * (sum(intervals) / len(intervals)))
    assert 400 <= internal_wpm <= 520


def test_rhythm_has_controlled_arrhythmia() -> None:
    rhythm = RhythmEngine(TypingProfile(wpm=180, variation=30), random.Random(11))
    intervals = [sum(rhythm.keystroke_timing("а")) for _ in range(700)]
    mean = sum(intervals) / len(intervals)
    coefficient_of_variation = pstdev(intervals) / mean
    numerator = sum((a - mean) * (b - mean) for a, b in pairwise(intervals))
    denominator = sum((value - mean) ** 2 for value in intervals)
    assert 0.20 <= coefficient_of_variation <= 0.65
    assert 0.10 <= numerator / denominator <= 0.95


def test_enter_delay_is_small_at_max_speed() -> None:
    rhythm = RhythmEngine(TypingProfile(wpm=280), random.Random(9))
    before = [rhythm.before_send_pause() for _ in range(100)]
    after = [rhythm.between_messages_pause(100) for _ in range(100)]
    assert max(before) < 0.025
    assert max(after) < 0.070


def test_slower_profiles_keep_a_small_gap() -> None:
    rhythm = RhythmEngine(TypingProfile(wpm=80), random.Random(3))
    assert rhythm.between_messages_pause(20) >= 0.010


def test_profile_clamps_untrusted_values() -> None:
    profile = TypingProfile(wpm=9999, variation=-2, typo_rate=100).normalized()
    assert (profile.wpm, profile.variation, profile.typo_rate) == (300, 0, 40.0)
