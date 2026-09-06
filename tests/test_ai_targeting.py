from __future__ import annotations

import asyncio
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from typerx.ai import AIError, ReplyLoop, defaults
from typerx.targeting import SenderGateway, SenderRuntime, message_row, target_context


def message(number, sender_id=7, *, out=False, bot=False, text="Hello"):
    sender = SimpleNamespace(first_name="Alex", last_name="", bot=bot, is_self=out, deleted=False)
    return SimpleNamespace(id=number, sender_id=sender_id, sender=sender, out=out, raw_text=text)


class RowTests(unittest.TestCase):
    def test_sender_id_is_preserved_not_just_display_name(self):
        self.assertEqual(message_row(message(1))["sender_id"], 7)
        self.assertEqual(message_row(message(1))["sender_name"], "Alex")

    def test_own_bot_and_anonymous_are_not_targets(self):
        for row in [message(1, out=True), message(2, bot=True), message(3, -1001)]:
            self.assertFalse(message_row(row)["can_target"])
        row = message(4)
        row.sender = None
        self.assertFalse(message_row(row)["can_target"])

    def test_context_excludes_other_people_and_our_replies(self):
        rows = [message_row(message(1, 7)), message_row(message(2, 8)),
                message_row(message(3, 9, out=True)), message_row(message(4, 7))]
        self.assertEqual([r["id"] for r in target_context(rows, 7)], [1, 4])

    def test_missing_sender_fails_closed(self):
        for sender in [None, 0, -12, "7"]:
            with self.assertRaises(AIError):
                target_context([], sender)


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_sender_in_different_chat_is_ignored(self):
        gateway = SenderGateway(None, lambda *_: None)
        gateway.target, gateway.target_sender = -1001, 7
        received = []
        gateway.on_message = received.append
        for chat, sender, outgoing in [(-1001, 7, False), (-1001, 8, False),
                                        (-1002, 7, False), (-1001, 7, True)]:
            await gateway._incoming(SimpleNamespace(id=1, chat_id=chat, sender_id=sender,
                                                     out=outgoing, raw_text="Hi"))
        self.assertEqual(received, [1])
        gateway.target_sender = None
        await gateway._incoming(SimpleNamespace(id=2, chat_id=-1001, sender_id=7, out=False, raw_text="Hi"))
        self.assertEqual(received, [1])

    async def test_loaded_history_includes_all_but_active_history_is_filtered(self):
        gateway = SenderGateway(None, lambda *_: None)
        gateway.peers[-1001] = "group"
        gateway.client = SimpleNamespace(get_messages=AsyncMock(return_value=[
            message(3, 9, out=True), message(2, 8), message(1, 7)]))
        rows = await gateway.history(-1001)
        self.assertEqual([row["id"] for row in rows], [1, 2, 3])
        gateway.target, gateway.target_sender = -1001, 7
        rows = await gateway.history(-1001)
        self.assertEqual([row["id"] for row in rows], [1])
        gateway.client.get_messages.assert_awaited_with("group", limit=50)

    async def test_llm_payload_contains_only_target_messages(self):
        gateway = SenderGateway(None, lambda *_: None)
        gateway.peers[-1001] = "group"
        gateway.target, gateway.target_sender = -1001, 7
        gateway.client = SimpleNamespace(get_messages=AsyncMock(return_value=[
            message(3, 8, text="OTHER PERSON"), message(2, 9, out=True, text="OUR REPLY"),
            message(1, 7, text="TARGET ONLY")]))
        llm = SimpleNamespace(complete=AsyncMock(return_value="answer"))
        output = AsyncMock()
        loop = ReplyLoop(gateway, llm, output, SimpleNamespace(config=defaults(), secrets={}), lambda *_: None)
        loop.incoming(1)
        task = asyncio.create_task(loop.run(-1001))
        try:
            await asyncio.sleep(1.35)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(llm.complete.call_args.args[-1], [{"role": "user", "content": "TARGET ONLY"}])

    async def test_group_classification_excludes_forums_and_broadcasts(self):
        gateway = SenderGateway(None, lambda *_: None)
        gateway.peers = {-1: SimpleNamespace(), -2: SimpleNamespace(megagroup=True, forum=True),
                         -3: SimpleNamespace(broadcast=True), -4: SimpleNamespace(megagroup=True, broadcast=False)}
        chats = [{"id": key, "can_reply": False} for key in gateway.peers]
        with patch("typerx.ai.TelegramGateway.chats", AsyncMock(return_value=chats)):
            result = await gateway.chats()
        self.assertEqual([row["can_reply"] for row in result], [True, False, False, True])


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.runtime = SenderRuntime(self.root.name, lambda *_: None)
        self.runtime.chat_list = [{"id": -1001, "name": "Team", "can_reply": True, "kind": "group"},
                                  {"id": 22, "name": "Private", "can_reply": True, "kind": "private"}]
        self.runtime.telegram.history = AsyncMock(return_value=[message_row(message(1, 7)), message_row(message(2, 8)),
                                                                message_row(message(3, 9, out=True))])

    def tearDown(self):
        self.runtime.close()
        self.root.cleanup()

    def dispatch(self, operation, data):
        return asyncio.run_coroutine_threadsafe(self.runtime.dispatch(operation, data), self.runtime.loop).result(5)

    def test_click_resolves_author_from_server_history(self):
        self.dispatch("select", {"id": -1001})
        target = self.dispatch("select_sender", {"message_id": 1, "sender_id": 999, "sender_name": "forged"})
        self.assertEqual(target["sender_id"], 7)
        self.assertEqual(target["sender_name"], "Alex")
        self.assertEqual(target["id"], -1001)
        self.assertEqual(target["name"], "Team")  # GUI guard must bind the group, not the person's DM.

    def test_unknown_message_and_own_message_are_rejected(self):
        self.dispatch("select", {"id": -1001})
        for number in [999, 3]:
            with self.assertRaises(AIError):
                self.dispatch("select_sender", {"message_id": number})

    def test_switch_chat_resets_sender_and_preparation(self):
        self.dispatch("select", {"id": -1001})
        self.dispatch("select_sender", {"message_id": 1})
        self.dispatch("prepare", {"mode": "ai", "consent": True})
        self.dispatch("select", {"id": 22})
        self.assertIsNone(self.runtime.target)
        self.assertIsNone(self.runtime.telegram.target_sender)
        self.assertFalse(self.runtime.prepared)

    def test_click_different_person_with_same_name_switches_id(self):
        self.dispatch("select", {"id": -1001})
        self.dispatch("select_sender", {"message_id": 1})
        target = self.dispatch("select_sender", {"message_id": 2})
        self.assertEqual(target["sender_id"], 8)
        self.assertEqual(target["sender_name"], "Alex")

    def test_clear_requires_selecting_again(self):
        self.dispatch("select", {"id": -1001})
        self.dispatch("select_sender", {"message_id": 1})
        self.dispatch("clear_target", {})
        with self.assertRaises(AIError):
            self.dispatch("prepare", {"mode": "ai", "consent": True})


if __name__ == "__main__":
    unittest.main()
