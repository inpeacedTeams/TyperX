from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class TypingProfile:
    name: str = "Natural"
    wpm: int = 105
    variation: int = 24
    typo_rate: float = 12.0
    words_per_message: int = 5
    smart_split: bool = True
    single_message: bool = False
    fix_typos: bool = True
    correct_typos: bool = True
    punctuation_pauses: bool = True
    keep_punctuation: bool = True
    auto_123_challenge: bool = False
    countdown_seconds: int = 3

    def normalized(self) -> "TypingProfile":
        return TypingProfile(
            name=self.name[:40] or "Natural",
            wpm=max(25, min(300, int(self.wpm))),
            variation=max(0, min(55, int(self.variation))),
            typo_rate=max(0.0, min(40.0, float(self.typo_rate))),
            words_per_message=max(1, min(16, int(self.words_per_message))),
            smart_split=bool(self.smart_split),
            single_message=bool(self.single_message),
            fix_typos=bool(self.fix_typos),
            correct_typos=bool(self.correct_typos),
            punctuation_pauses=bool(self.punctuation_pauses),
            keep_punctuation=bool(self.keep_punctuation),
            auto_123_challenge=bool(self.auto_123_challenge),
            countdown_seconds=max(0, min(10, int(self.countdown_seconds))),
        )


@dataclass(slots=True)
class TextTemplate:
    id: str
    title: str
    text: str
    category: str = "Мои"
    builtin: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "TextTemplate":
        return cls(
            id=str(raw.get("id", "")),
            title=str(raw.get("title", "Без названия"))[:80],
            text=str(raw.get("text", ""))[:100_000],
            category=str(raw.get("category", "Мои"))[:40],
            builtin=bool(raw.get("builtin", False)),
        )


@dataclass(slots=True)
class AppState:
    schema_version: int = 5
    profile: TypingProfile = field(default_factory=TypingProfile)
    templates: list[TextTemplate] = field(default_factory=list)
    selected_template_id: str = ""
    window_width: int = 1240
    window_height: int = 780

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
