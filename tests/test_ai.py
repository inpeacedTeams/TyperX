from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from typerx.ai import AIError, AIStore, OpenAIClient, ReplyLoop, TelegramGateway, defaults, endpoint, validate
from typerx.ai_runtime import Runtime, friendly_error


class ConfigTests(unittest.TestCase):
    def test_endpoints(self):
        self.assertEqual(endpoint("https://example.com/v1/"), "https://example.com/v1/chat/completions")
        self.assertEqual(endpoint("http://127.0.0.1:1234/v1"), "http://127.0.0.1:1234/v1/chat/completions")
        for value in ["http://example.com/v1", "https://user:secret@example.com", "file:///tmp/x", "https://x/?key=secret"]:
            with self.assertRaises(AIError):
                endpoint(value)

    def test_preset_validation_and_bounds(self):
        raw = defaults()
        raw.update(wpm=999, words=0)
        fixed = validate(raw)
        self.assertEqual((fixed["wpm"], fixed["words"]), (300, 1))
        raw["presets"].append(dict(raw["presets"][0]))
        with self.assertRaises(AIError):
            validate(raw)

    def test_invalid_active_preset(self):
        raw = defaults()
        raw["active_preset"] = "missing"
        with self.assertRaises(AIError):
            validate(raw)

    def test_multi_persona_and_no_mutation(self):
        raw = defaults()
        raw["presets"][0]["prompts"] = ["Первый", "Второй"]
        validate(raw)["presets"][0]["prompts"].append("Третий")
        self.assertEqual(len(raw["presets"][0]["prompts"]), 2)

    def test_local_round_trip(self):
        with tempfile.TemporaryDirectory() as root:
            store = AIStore(root)
            raw = defaults()
            raw["wpm"] = 80
            store.save(raw)
            self.assertEqual(AIStore(root).config["wpm"], 80)
            self.assertFalse(list(Path(root).glob(".ai-*")))

    def test_corrupt_config_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "ai.json"
            path.write_text("broken", encoding="utf-8")
            self.assertTrue(AIStore(root).warning)
            self.assertEqual(path.read_text(), "broken")

    def test_secrets_never_in_public_config(self):
        crypto = SimpleNamespace(CryptProtectData=lambda data, *_: b"encrypted:" + data,
                                 CryptUnprotectData=lambda data, *_: ("", data[len(b"encrypted:"):]))
        with tempfile.TemporaryDirectory() as root, patch.dict(sys.modules, {"win32crypt": crypto}):
            store = AIStore(root)
            raw = {**defaults(), "api_key": "SECRET", "api_hash": "HASH"}
            store.save(raw)
            self.assertNotIn("SECRET", json.dumps(store.public()))
            self.assertNotIn("SECRET", (Path(root) / "ai.json").read_text())
            loaded = AIStore(root)
            self.assertEqual(loaded.secrets["api_key"], "SECRET")
            loaded.save({**loaded.config, "api_key": ""})
            self.assertEqual(loaded.secrets["api_key"], "SECRET")
            loaded.save({**loaded.config, "clear_api_key": True})
            self.assertNotIn("api_key", loaded.secrets)

    def test_errors_do_not_echo_credentials(self):
        self.assertNotIn("SECRET", friendly_error(RuntimeError("SECRET")))


class AsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_telegram_only_selected_incoming_human(self):
        gateway = TelegramGateway(None, lambda *_: None)
        gateway.target = 42
        ids = []
        gateway.on_message = ids.append
        for chat, sender, outgoing, text in [(42, 42, False, "hello"), (43, 43, False, "no"),
                                              (42, 42, True, "echo"), (42, 9, False, "wrong"),
                                              (42, 42, False, "")]:
            await gateway._incoming(SimpleNamespace(id=7, chat_id=chat, sender_id=sender,
                                                     out=outgoing, raw_text=text))
        self.assertEqual(ids, [7])
        gateway.target = None
        await gateway._incoming(SimpleNamespace(id=8, chat_id=42, sender_id=42, out=False, raw_text="x"))
        self.assertEqual(ids, [7])

    async def test_llm_uses_all_personas_and_last_50_messages(self):
        config = defaults()
        config["presets"][0]["prompts"] = ["Первый", "Второй"]
        def capture(url, key, payload):
            messages = json.loads(payload)["messages"]
            self.assertEqual(len(messages), 51)
            self.assertIn("Первый\n\nВторой", messages[0]["content"])
            self.assertEqual(messages[1]["content"], "10")
            return "ok"
        client = OpenAIClient()
        history = [{"role": "user", "content": str(i)} for i in range(60)]
        with patch.object(client, "_request", capture):
            self.assertEqual(await client.complete(config, "", history), "ok")

    async def test_connection_test_excludes_history(self):
        def capture(url, key, payload):
            self.assertNotIn("PRIVATE CHAT", payload.decode())
            return "OK"
        with patch.object(OpenAIClient, "_request", staticmethod(capture)):
            await OpenAIClient().complete(defaults(), "", [{"role": "user", "content": "PRIVATE CHAT"}], check=True)

    def make_loop(self):
        telegram = SimpleNamespace(history=AsyncMock(return_value=[{"id": 1, "role": "user", "content": "Hi"}]))
        llm = SimpleNamespace(complete=AsyncMock(return_value="Hello"))
        output = AsyncMock()
        store = SimpleNamespace(config=defaults(), secrets={})
        return ReplyLoop(telegram, llm, output, store, lambda *_: None)

    async def test_no_reply_on_startup(self):
        loop = self.make_loop()
        task = asyncio.create_task(loop.run(42))
        await asyncio.sleep(0.02)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        loop.llm.complete.assert_not_called()
        loop.output.assert_not_called()

    async def test_deduplicates_incoming_events(self):
        loop = self.make_loop()
        loop.incoming(5)
        loop.incoming(5)
        loop.incoming(4)
        self.assertEqual((loop.latest, loop.revision), (5, 1))

    async def test_one_reply_and_duplicate_is_ignored(self):
        loop = self.make_loop()
        loop.incoming(1)
        task = asyncio.create_task(loop.run(42))
        await asyncio.sleep(1.35)
        loop.incoming(1)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        loop.output.assert_awaited_once_with("Hello")

    async def test_cancel_during_generation_never_types(self):
        loop = self.make_loop()
        started = asyncio.Event()
        async def blocked(*args):
            started.set()
            await asyncio.Event().wait()
        loop.llm.complete = blocked
        loop.incoming(1)
        task = asyncio.create_task(loop.run(42))
        await asyncio.wait_for(started.wait(), timeout=3)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        loop.output.assert_not_called()

    async def test_new_message_discards_stale_generation(self):
        loop = self.make_loop()
        async def changed(*args):
            loop.incoming(2)
            return "stale"
        loop.llm.complete = changed
        loop.incoming(1)
        task = asyncio.create_task(loop.run(42))
        await asyncio.sleep(1.35)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        loop.output.assert_not_called()

    async def test_missing_history_fails_closed(self):
        loop = self.make_loop()
        loop.telegram.history.return_value = []
        loop.incoming(1)
        with self.assertRaises(AIError):
            await asyncio.wait_for(loop.run(42), timeout=3)
        loop.output.assert_not_called()

    async def test_future_context_is_not_sent(self):
        loop = self.make_loop()
        loop.telegram.history.return_value += [{"id": 2, "role": "user", "content": "future"}]
        loop.incoming(1)
        task = asyncio.create_task(loop.run(42))
        await asyncio.sleep(1.35)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        history = loop.llm.complete.call_args.args[-1]
        self.assertEqual(history, [{"role": "user", "content": "Hi"}])

    async def test_runtime_rejects_unknown_operation(self):
        with tempfile.TemporaryDirectory() as root:
            runtime = Runtime(root, lambda *_: None)
            try:
                with self.assertRaises(AIError):
                    await runtime.dispatch("send_message", {})
            finally:
                runtime.close()

    async def test_requires_preparation(self):
        with tempfile.TemporaryDirectory() as root:
            runtime = Runtime(root, lambda *_: None)
            try:
                with self.assertRaises(AIError):
                    await runtime.dispatch("start", {})
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
