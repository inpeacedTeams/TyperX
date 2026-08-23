import random

from typerx.domain.typos import TypoPlanner
from typerx.services.monkeytype_pacing import (
    SAFE_RAW_WPM,
    emitted_event_count,
    event_interval_seconds,
    fit_typos_to_raw_limit,
    scored_character_count,
)


def _observed_wpms(text: str, target: int, typos: dict, corrected: bool) -> tuple[float, float]:
    interval = event_interval_seconds(text, target, typos, corrected)
    duration = interval * emitted_event_count(text, typos, corrected)
    scored = scored_character_count(text, typos, corrected)
    return scored / 5 / (duration / 60), len(text) / 5 / (duration / 60)


def test_no_typos_targets_selected_wpm() -> None:
    text = "alpha beta gamma delta " * 20
    wpm, raw = _observed_wpms(text, 300, {}, False)
    assert wpm == 300
    assert raw == 300


def test_uncorrected_typos_keep_target_without_invalid_raw() -> None:
    text = "alpha beta gamma delta epsilon " * 20
    planned = TypoPlanner(40, random.Random(4), corrections_only=True).plan(text)
    fitted = fit_typos_to_raw_limit(text, 300, planned, False)
    wpm, raw = _observed_wpms(text, 300, fitted, False)
    assert wpm == 300
    assert raw <= SAFE_RAW_WPM
    assert fitted
    assert len(fitted) < len(planned)


def test_lower_speed_keeps_more_visible_errors() -> None:
    text = "alpha beta gamma delta epsilon " * 20
    planned = TypoPlanner(40, random.Random(9), corrections_only=True).plan(text)
    at_200 = fit_typos_to_raw_limit(text, 200, planned, False)
    at_300 = fit_typos_to_raw_limit(text, 300, planned, False)
    assert len(at_200) >= len(at_300)


def test_corrected_typos_do_not_need_raw_pruning() -> None:
    text = "alpha beta gamma delta epsilon " * 20
    planned = TypoPlanner(40, random.Random(7), corrections_only=True).plan(text)
    assert fit_typos_to_raw_limit(text, 300, planned, True) == planned
