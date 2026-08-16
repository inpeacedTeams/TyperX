import random

from typerx.domain.models import TypingProfile
from typerx.domain.rhythm import RhythmEngine


def test_delays_are_bounded() -> None:
    rhythm = RhythmEngine(TypingProfile(wpm=280, variation=55), random.Random(1))
    values = [rhythm.character_delay("а") for _ in range(1000)]
    assert min(values) >= 0.012
    assert max(values) <= 0.95


def test_punctuation_is_slower_than_letters() -> None:
    letter = RhythmEngine(TypingProfile(), random.Random(4)).character_delay("а")
    mark = RhythmEngine(TypingProfile(), random.Random(4)).character_delay(".")
    assert mark > letter


def test_profile_clamps_untrusted_values() -> None:
    p = TypingProfile(wpm=9999, variation=-2, typo_rate=100).normalized()
    assert (p.wpm, p.variation, p.typo_rate) == (280, 0, 7.0)
