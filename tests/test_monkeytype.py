import threading

from typerx.services.monkeytype_service import MonkeytypeInbox


def test_inbox_normalizes_browser_text() -> None:
    inbox = MonkeytypeInbox()
    inbox.put("hello   world\nnext")
    assert inbox.wait(threading.Event()) == "hello world next"


def test_inbox_ignores_empty_payload() -> None:
    inbox = MonkeytypeInbox()
    inbox.put("   ")
    cancel = threading.Event()
    cancel.set()
    try:
        inbox.wait(cancel)
    except Exception as exc:
        assert exc.__class__.__name__ == "TypingCancelled"
    else:
        raise AssertionError("empty payload must not wake the inbox")
