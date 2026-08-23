import threading

import pytest

from typerx.services.monkeytype_service import MonkeytypeInbox
from typerx.services.typing_service import TypingCancelled
from typerx.ui.monkeytype_page import estimate_seconds, format_duration, typo_frequency_label


def test_inbox_normalizes_browser_text() -> None:
    inbox = MonkeytypeInbox()
    inbox.put("hello   world\nnext")
    assert inbox.wait(threading.Event()) == "hello world next"


def test_inbox_ignores_empty_payload() -> None:
    inbox = MonkeytypeInbox()
    inbox.put("   ")
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(TypingCancelled):
        inbox.wait(cancel)


def test_session_forecast_accounts_for_speed_and_typos() -> None:
    assert estimate_seconds(250, 300, 0) < estimate_seconds(250, 100, 0)
    assert estimate_seconds(250, 300, 12) > estimate_seconds(250, 300, 0)


def test_duration_is_human_readable() -> None:
    assert format_duration(29.2) == "≈ 29 сек"
    assert format_duration(91) == "≈ 1 мин 31 сек"


def test_typo_frequency_labels_are_clear() -> None:
    assert typo_frequency_label(0) == "Без опечаток"
    assert typo_frequency_label(12) == "Естественные"
    assert typo_frequency_label(40) == "Очень частые"
