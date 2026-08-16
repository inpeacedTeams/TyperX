from typerx.domain.models import TypingProfile
from typerx.domain.splitter import SmartSplitter


def test_expected_conversation_shape() -> None:
    text = "Привет как дела что делаешь чем занимаешься я например учу уроки."
    plan = SmartSplitter().plan(text, TypingProfile(), seed=7)
    assert plan.messages[:4] == ("Привет", "как дела", "что делаешь", "чем занимаешься")
    assert " ".join(plan.messages).replace("  ", " ") == text


def test_empty_text_is_safe() -> None:
    assert SmartSplitter().plan("  \n ", TypingProfile()).messages == ()


def test_manual_mode_uses_lines() -> None:
    profile = TypingProfile(smart_split=False)
    assert SmartSplitter().plan("one\ntwo", profile).messages == ("one", "two")


def test_punctuation_can_be_removed() -> None:
    profile = TypingProfile(keep_punctuation=False)
    assert SmartSplitter().plan("Привет. Как дела?", profile, seed=1).messages == ("Привет", "Как дела")
