from __future__ import annotations

import json
import random
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from typerx.domain.models import TypingProfile
from typerx.domain.rhythm import RhythmEngine
from typerx.domain.splitter import SplitPlan
from typerx.domain.typing_physics import finger_for_key
from typerx.domain.typos import TypoPlanner
from typerx.platform.interception_keyboard import InterceptionKeyboard, PressedKey
from typerx.services.typing_service import TypingCancelled, TypingService


class MonkeytypeInbox:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._text = ""

    def put(self, text: str) -> None:
        cleaned = " ".join(text.split())[:50_000]
        if not cleaned:
            return
        with self._lock:
            self._text = cleaned
        self._event.set()

    def wait(self, cancel: threading.Event) -> str:
        while not self._event.wait(0.05):
            if cancel.is_set():
                raise TypingCancelled
        with self._lock:
            return self._text


class MonkeytypeBridge:
    HOST = "127.0.0.1"
    PORT = 8765

    def __init__(self, inbox: MonkeytypeInbox) -> None:
        self.inbox = inbox
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        inbox = self.inbox

        class Handler(BaseHTTPRequestHandler):
            def do_OPTIONS(self) -> None:
                self.send_response(204)
                self._cors()
                self.end_headers()

            def do_POST(self) -> None:
                if self.path != "/monkeytype":
                    self.send_error(404)
                    return
                origin = self.headers.get("Origin", "")
                if origin not in {
                    "https://monkeytype.com",
                    "https://www.monkeytype.com",
                    "http://localhost:5000",
                }:
                    self.send_error(403)
                    return
                try:
                    size = min(int(self.headers.get("Content-Length", "0")), 100_000)
                    payload = json.loads(self.rfile.read(size))
                    text = str(payload.get("text", ""))
                except (ValueError, TypeError):
                    self.send_error(400)
                    return
                inbox.put(text)
                self.send_response(204)
                self._cors()
                self.end_headers()

            def _cors(self) -> None:
                self.send_header(
                    "Access-Control-Allow-Origin",
                    self.headers.get("Origin", ""),
                )
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")

            def log_message(self, _format: str, *args: object) -> None:
                del args

        self.server = ThreadingHTTPServer((self.HOST, self.PORT), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="typerx-monkeytype-bridge",
            daemon=True,
        )
        self.thread.start()

    def close(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=1.0)


class MonkeytypeService(TypingService):
    MAX_HELD_KEYS = 3

    def run(
        self,
        plan: SplitPlan,
        profile: TypingProfile,
        target_window: int,
        progress: Callable[[int, int], None],
    ) -> None:
        del plan
        self._cancel.clear()
        self._pause_requested.clear()
        self._paused.clear()
        inbox = MonkeytypeInbox()
        bridge = MonkeytypeBridge(inbox)
        bridge.start()
        output = InterceptionKeyboard(target_window)
        pending: list[tuple[float, PressedKey, str]] = []
        try:
            text = inbox.wait(self._cancel)
            progress(1, 1)
            rng = random.Random()
            normalized = profile.normalized()
            rhythm = RhythmEngine(normalized, rng)
            typo_planner = TypoPlanner(
                normalized.typo_rate if normalized.fix_typos else 0.0,
                rng,
                correct_typos=True,
                correction_only=True,
            )
            typos = typo_planner.plan(text)
            previous: str | None = None

            def release_entry(entry: tuple[float, PressedKey, str]) -> None:
                output.release(entry[1])
                pending.remove(entry)

            def wait_until(deadline: float) -> None:
                while pending:
                    entry = min(pending, key=lambda item: item[0])
                    if entry[0] > deadline:
                        break
                    self._wait(max(0.0, entry[0] - time.perf_counter()))
                    release_entry(entry)
                self._wait(max(0.0, deadline - time.perf_counter()))

            def flush_pending() -> None:
                while pending:
                    entry = min(pending, key=lambda item: item[0])
                    self._wait(max(0.0, entry[0] - time.perf_counter()))
                    release_entry(entry)

            def make_physical_room(value: str) -> None:
                now = time.perf_counter()
                for entry in sorted(pending, key=lambda item: item[0]):
                    if entry[0] <= now:
                        release_entry(entry)
                finger = finger_for_key(value)
                conflict = next(
                    (
                        entry
                        for entry in sorted(pending, key=lambda item: item[0])
                        if entry[2] == finger
                    ),
                    None,
                )
                if conflict is not None:
                    wait_until(conflict[0])
                if len(pending) >= self.MAX_HELD_KEYS:
                    wait_until(min(entry[0] for entry in pending))

            def emit(value: str, press: Callable[[], PressedKey]) -> None:
                nonlocal previous
                self._check()
                make_physical_room(value)
                dwell, flight = rhythm.keystroke_timing(value, previous)
                down_at = time.perf_counter()
                key = press()
                pending.append((down_at + dwell, key, finger_for_key(value)))
                wait_until(down_at + max(0.018, dwell + flight))
                previous = value

            def emit_char(value: str) -> None:
                emit(value, lambda: output.press(value))

            def emit_backspace() -> None:
                emit("\b", output.press_backspace)

            for index, char in enumerate(text):
                typo = typos.get(index)
                if typo is not None and typo.replacement:
                    emit_char(typo.replacement)
                    flush_pending()
                    before, after = rhythm.correction_pause()
                    self._wait(before)
                    emit_backspace()
                    flush_pending()
                    self._wait(after)

                emit_char(char)
                boundary = char.isspace() or index == len(text) - 1
                if boundary:
                    flush_pending()
                self._pause_on_word_boundary(boundary)
            flush_pending()
        finally:
            for _, key, _ in pending:
                try:
                    output.release(key)
                except Exception:
                    pass
            output.close()
            bridge.close()
