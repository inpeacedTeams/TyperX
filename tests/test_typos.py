import random

from typerx.domain.typos import TypoKind, TypoPlanner


def test_zero_rate_never_mutates() -> None:
    assert TypoPlanner(0, random.Random(1)).plan("привет как дела") == {}


def test_high_rate_produces_at_most_one_typo_per_word() -> None:
    actions = TypoPlanner(40, random.Random(3)).plan("привет сегодня занимаешься уроками")
    assert actions
    words = [(0, 6), (7, 14), (15, 26), (27, 34)]
    for start, end in words:
        assert sum(start <= index < end for index in actions) <= 1


def test_typo_types_are_chat_realistic() -> None:
    kinds = set()
    for seed in range(100):
        kinds.update(action.kind for action in TypoPlanner(40, random.Random(seed)).plan("привет делаешь уроки").values())
    assert {TypoKind.OMIT, TypoKind.SUBSTITUTE, TypoKind.CORRECTED} <= kinds
