import threading

import pytest

from typerx.services.monkeytype_service import MonkeytypeInbox
from typerx.services.typing_service import TypingCancelled


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
