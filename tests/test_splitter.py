from typerx.domain.models import TypingProfile
from typerx.domain.splitter import SmartSplitter


def test_expected_conversation_shape() -> None:
    text = "Привет как дела что делаешь чем занимаешься я например учу уроки."
    plan = SmartSplitter().plan(text, TypingProfile(words_per_message=5), seed=7)
    assert plan.messages[:4] == ("Привет", "как дела", "что делаешь", "чем занимаешься")
    assert " ".join(plan.messages).replace("  ", " ") == text


def test_two_word_target_stays_close() -> None:
    text = "сегодня вечером я буду спокойно учить сложные уроки дома"
    plan = SmartSplitter().plan(text, TypingProfile(words_per_message=2), seed=11)
    sizes = [len(message.split()) for message in plan.messages]
    assert all(1 <= size <= 4 for size in sizes)
    assert sum(sizes) == len(text.split())
    assert sum(size == 2 for size in sizes) >= 2


def test_target_is_not_a_robotic_hard_cut() -> None:
    text = "один два три четыре пять шесть семь восемь девять"
    plan = SmartSplitter().plan(text, TypingProfile(words_per_message=3), seed=2)
    assert set(map(lambda item: len(item.split()), plan.messages)) <= {1, 2, 3, 4, 5}


def test_empty_text_is_safe() -> None:
    assert SmartSplitter().plan("  \n ", TypingProfile()).messages == ()


def test_manual_mode_uses_lines() -> None:
    profile = TypingProfile(smart_split=False)
    assert SmartSplitter().plan("one\ntwo", profile).messages == ("one", "two")


def test_punctuation_can_be_removed() -> None:
    profile = TypingProfile(keep_punctuation=False)
    assert SmartSplitter().plan("Привет. Как дела?", profile, seed=1).messages == ("Привет", "Как дела")
