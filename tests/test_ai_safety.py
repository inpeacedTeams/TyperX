from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from typerx.ai import AIError
from typerx.ai_runtime import Runtime, TargetGuard


class FocusTests(unittest.TestCase):
    def make_guard(self):
        guard = TargetGuard.__new__(TargetGuard)
        guard.hwnd, guard.title, guard.peer_name = 12, "Alice", "Alice"
        guard.focus_id = (1, 2, 3)
        return guard

    def test_changed_window_rejected(self):
        fake = SimpleNamespace(GetForegroundWindow=lambda: 13, GetWindowText=lambda _: "Alice")
        with patch.dict(sys.modules, {"win32gui": fake}), self.assertRaises(AIError):
            self.make_guard().check()

    def test_same_window_different_chat_rejected(self):
        fake = SimpleNamespace(GetForegroundWindow=lambda: 12, GetWindowText=lambda _: "Bob")
        with patch.dict(sys.modules, {"win32gui": fake}), self.assertRaises(AIError):
            self.make_guard().check()

    def test_changed_editor_rejected(self):
        guard = self.make_guard()
        with patch.object(guard, "check"), patch("typerx.ai_runtime.focused_editor", return_value=((9,), "")):
            with self.assertRaises(AIError):
                guard.check_field()

    def test_existing_draft_rejected_before_output(self):
        guard = self.make_guard()
        with patch.object(guard, "check"), patch("typerx.ai_runtime.focused_editor", return_value=((1, 2, 3), "draft")):
            with self.assertRaises(AIError):
                guard.check_field(empty=True)
            guard.check_field()  # During typing our own draft is expected.


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.events = []
        self.runtime = Runtime(self.directory.name, self.events.append)

    def tearDown(self):
        self.runtime.close()
        self.directory.cleanup()

    def run_async(self, coroutine):
        return asyncio.run_coroutine_threadsafe(coroutine, self.runtime.loop).result(timeout=5)

    def test_invalid_preparation_clears_previous_arming(self):
        async def scenario():
            await self.runtime.dispatch("prepare", {"mode": "manual", "text": "ok"})
            self.assertTrue(self.runtime.prepared)
            with self.assertRaises(AIError):
                await self.runtime.dispatch("prepare", {"mode": "manual", "text": ""})
            self.assertFalse(self.runtime.prepared)
        self.run_async(scenario())

    def test_stop_event_is_set_synchronously(self):
        self.runtime.stopped.clear()
        self.runtime.stop()
        self.assertTrue(self.runtime.stopped.is_set())

    def test_queued_start_from_before_f9_is_rejected(self):
        async def scenario():
            old_epoch = self.runtime.epoch
            self.runtime.stop()
            with patch.object(self.runtime, "dispatch", new_callable=AsyncMock) as dispatch:
                await self.runtime._request("old-f8", "start", {}, old_epoch)
                dispatch.assert_not_awaited()
            response = next(event for event in self.events if event.get("id") == "old-f8")
            self.assertFalse(response["ok"])
        self.run_async(scenario())

    def test_stop_does_not_wait_for_request_lock(self):
        async def scenario():
            async with self.runtime.request_lock:
                self.runtime.stopped.clear()
                self.runtime.stop()
                await asyncio.sleep(0)
                self.assertTrue(self.runtime.stopped.is_set())
                self.assertFalse(self.runtime.prepared)
        self.run_async(scenario())

    def test_repeated_stop_does_not_cancel_cleanup_twice(self):
        async def scenario():
            started, cleaning, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
            async def worker():
                try:
                    started.set()
                    await asyncio.Event().wait()
                finally:
                    cleaning.set()
                    await release.wait()
            self.runtime.job = asyncio.create_task(worker())
            await started.wait()
            self.runtime.stop()
            await cleaning.wait()
            self.runtime.stop()
            await asyncio.sleep(0)
            self.assertEqual(self.runtime.job.cancelling(), 1)
            release.set()
            await asyncio.gather(self.runtime.job, return_exceptions=True)
        self.run_async(scenario())

    def test_reconfiguration_is_blocked_while_job_active(self):
        async def scenario():
            self.runtime.job = asyncio.create_task(asyncio.sleep(60))
            try:
                for operation in ["save", "select", "logout", "prepare"]:
                    with self.assertRaises(AIError):
                        await self.runtime.dispatch(operation, {})
            finally:
                self.runtime.stop()
                await asyncio.sleep(0)
                await asyncio.gather(self.runtime.job, return_exceptions=True)
        self.run_async(scenario())

    def test_focus_failure_cancels_worker_and_sets_stop(self):
        async def scenario():
            cancelled = asyncio.Event()
            async def writer(_):
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
            async def monitor():
                await asyncio.sleep(0)
                raise AIError("focus changed")
            self.runtime.mode = "manual"
            self.runtime.stopped.clear()
            with patch.object(self.runtime, "_output", writer), patch.object(self.runtime, "_monitor", monitor):
                await self.runtime._run()
            self.assertTrue(cancelled.is_set())
            self.assertTrue(self.runtime.stopped.is_set())
            self.assertEqual(self.runtime.stage, "error")
        self.run_async(scenario())

    def test_shutdown_is_idempotent_and_joins_thread(self):
        self.assertTrue(self.runtime.thread.is_alive())
        self.runtime.close()
        self.assertFalse(self.runtime.thread.is_alive())
        self.runtime.close()


if __name__ == "__main__":
    unittest.main()
