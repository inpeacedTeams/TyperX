from __future__ import annotations

_FINGER_ROWS = {
    "lp": "qazйфя",
    "lr": "wsxцыч",
    "lm": "edcувс",
    "li": "rfvtgbкамепи",
    "ri": "yhnujmнгртоь",
    "rm": "ik,шлб",
    "rr": "ol.щдю",
    "rp": "p;/'[]\\зжэ",
}
_FINGER_BY_CHAR = {
    char: finger for finger, chars in _FINGER_ROWS.items() for char in chars
}


def finger_for_key(char: str) -> str:
    """Return a stable physical-finger bucket for overlap constraints."""
    folded = char.casefold()
    if folded.isspace():
        return "thumb"
    if folded in "\b\n":
        return "rp"
    return _FINGER_BY_CHAR.get(folded, f"other:{folded}")
