import random

from typerx.domain.typos import TypoPlanner
from typerx.services.monkeytype_pacing import (
    emitted_event_count,
    event_interval_seconds,
    scored_character_count,
)


def test_no_typos_targets_selected_wpm() -> None:
    text = "alpha beta gamma delta " * 20
    interval = event_interval_seconds(text, 300, {}, False)
    duration = interval * emitted_event_count(text, {}, False)
    observed = scored_character_count(text, {}, False) / 5 / (duration / 60)
    assert observed == 300


def test_uncorrected_typos_are_compensated_in_final_wpm() -> None:
    text = "alpha beta gamma delta epsilon " * 20
    typos = TypoPlanner(20, random.Random(4), corrections_only=True).plan(text)
    interval = event_interval_seconds(text, 300, typos, False)
    duration = interval * emitted_event_count(text, typos, False)
    observed = scored_character_count(text, typos, False) / 5 / (duration / 60)
    assert observed == 300
    assert interval < event_interval_seconds(text, 300, {}, False)


def test_corrections_are_budgeted_without_lowering_wpm() -> None:
    text = "alpha beta gamma delta epsilon " * 20
    typos = TypoPlanner(20, random.Random(7), corrections_only=True).plan(text)
    corrected_interval = event_interval_seconds(text, 300, typos, True)
    clean_interval = event_interval_seconds(text, 300, {}, True)
    assert corrected_interval < clean_interval
