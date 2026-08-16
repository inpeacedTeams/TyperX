from __future__ import annotations

import random
import re
from dataclasses import dataclass

from typerx.domain.models import TypingProfile

_WORD_RE = re.compile(r"\S+")
_PARAGRAPH_RE = re.compile(r"\r?\n+")
_STRIP = " \t,\.!?…:;()[]{}\"'«»"
_QUESTION_CUES = {"как", "что", "чем", "где", "когда", "почему", "зачем", "кто", "куда", "откуда"}
_OPENERS = {"привет", "слушай", "смотри", "короче", "ладно", "кстати", "ну"}
_SUBJECT_CUES = {"я", "ты", "мы", "вы"}
_NO_BREAK_BEFORE = {"и", "а", "но", "или", "либо", "же", "бы", "что-то", "кто-то"}


@dataclass(frozen=True, slots=True)
class SplitPlan:
    messages: tuple[str, ...]

    @property
    def character_count(self) -> int:
        return sum(map(len, self.messages))


class SmartSplitter:
    """Conservative Russian message splitter.

    It scores natural boundaries instead of slicing on a random word count. Randomness only
    changes acceptable boundaries, so the preview stays readable and runs stay varied.
    """

    def plan(self, text: str, profile: TypingProfile, seed: int | None = None) -> SplitPlan:
        clean = text.strip()
        if not clean:
            return SplitPlan(())
        if not profile.smart_split:
            messages = tuple(x.strip() for x in _PARAGRAPH_RE.split(clean) if x.strip())
            return SplitPlan(self._punctuation(messages, profile.keep_punctuation))

        rng = random.Random(seed)
        output: list[str] = []
        for paragraph in _PARAGRAPH_RE.split(clean):
            words = _WORD_RE.findall(paragraph)
            if not words:
                continue
            start = 0
            target = rng.randint(5, 10)
            for index, raw in enumerate(words):
                count = index - start + 1
                token = raw.strip(_STRIP).casefold()
                next_token = (
                    words[index + 1].strip(_STRIP).casefold() if index + 1 < len(words) else ""
                )
                sentence_end = raw.endswith((".", "!", "?", "…"))
                natural_next = next_token in (_QUESTION_CUES | _OPENERS | _SUBJECT_CUES)
                current_opener = token in _OPENERS and count <= 2
                aside = token == "например" and count >= 2 and rng.random() < 0.46
                length_boundary = count >= target and next_token not in _NO_BREAK_BEFORE
                hard_limit = count >= 13

                should_break = sentence_end or aside or hard_limit
                should_break |= natural_next and count >= 1
                should_break |= current_opener and count == 1
                should_break |= length_boundary and count >= 4
                if should_break:
                    self._append(words[start : index + 1], output)
                    start = index + 1
                    target = rng.randint(5, 10)
            self._append(words[start:], output)

        messages = self._merge_fragments(output)
        return SplitPlan(self._punctuation(tuple(messages), profile.keep_punctuation))

    @staticmethod
    def _append(words: list[str], output: list[str]) -> None:
        value = " ".join(words).strip()
        if value:
            output.append(value)

    @staticmethod
    def _merge_fragments(messages: list[str]) -> list[str]:
        merged: list[str] = []
        for message in messages:
            word_count = len(message.split())
            if merged and word_count == 1 and message.casefold().strip(_STRIP) in _NO_BREAK_BEFORE:
                merged[-1] += " " + message
            else:
                merged.append(message)
        return merged

    @staticmethod
    def _punctuation(messages: tuple[str, ...], keep: bool) -> tuple[str, ...]:
        if keep:
            return messages
        return tuple(x.rstrip(".,!?…:;") for x in messages if x.rstrip(".,!?…:;"))
