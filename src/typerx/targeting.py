"""Select a sender from a displayed message; keep output bound to its original chat."""
from __future__ import annotations

from typerx.ai import AIError, TelegramGateway
from typerx.ai_runtime import Runtime


def message_row(message):
    sender = message.sender
    sender_id = message.sender_id
    outgoing = bool(message.out)
    is_person = (isinstance(sender_id, int) and sender_id > 0 and sender is not None
                 and not getattr(sender, "bot", False) and not getattr(sender, "is_self", False)
                 and not getattr(sender, "deleted", False) and not outgoing)
    name = " ".join(filter(None, [getattr(sender, "first_name", None),
                                  getattr(sender, "last_name", None)]))
    name = name or getattr(sender, "title", None) or getattr(sender, "username", None)
    return {"id": message.id, "sender_id": sender_id,
            "sender_name": "Вы" if outgoing else str(name or "Неизвестный автор"),
            "can_target": bool(is_person), "role": "assistant" if outgoing else "user",
            "content": message.raw_text[:6000]}


def target_context(rows, sender_id):
    """Fail closed: do not send other participants OR our own replies to the LLM."""
    if not isinstance(sender_id, int) or sender_id <= 0:
        raise AIError("Выбери автора сообщения как таргета")
    return [row for row in rows if row.get("sender_id") == sender_id
            and row.get("role") == "user" and row.get("can_target")]


class SenderGateway(TelegramGateway):
    def __init__(self, store, notify):
        super().__init__(store, notify)
        self.target_sender = None

    async def chats(self):
        chats = await super().chats()
        for chat in chats:
            entity = self.peers[chat["id"]]
            group = chat["id"] < 0 and (getattr(entity, "megagroup", False)
                                        or not hasattr(entity, "broadcast"))
            # A forum topic cannot be safely bound by the window title alone.
            group = group and not any(getattr(entity, key, False)
                                      for key in ("broadcast", "forum", "left", "deactivated"))
            chat["can_reply"] = bool(chat["can_reply"] or group)
            chat["kind"] = "group" if group else "private" if chat["id"] > 0 else "channel"
        return chats

    async def history(self, peer_id):
        if peer_id not in self.peers:
            raise AIError("Загрузи чаты и выбери собеседника")
        messages = await self.client.get_messages(self.peers[peer_id], limit=50)
        rows = [message_row(message) for message in reversed(messages) if message.raw_text]
        if self.target is not None:
            if peer_id != self.target:
                raise AIError("История другого чата недоступна активному циклу")
            return target_context(rows, self.target_sender)
        return rows

    async def _incoming(self, event):
        if (self.target is None or self.target_sender is None or event.out
                or event.chat_id != self.target or event.sender_id != self.target_sender
                or not event.raw_text):
            return
        if self.on_message:
            self.on_message(event.id)

    async def close(self, logout=False):
        self.target_sender = None
        await super().close(logout=logout)


class SenderRuntime(Runtime):
    def __init__(self, root, emit):
        super().__init__(root, emit)
        self.telegram = SenderGateway(self.store, self.notify)
        self.selected_chat = None
        self.displayed_messages = []

    def clear_target(self):
        self.prepared = False
        self.target = None
        self.telegram.target_sender = None

    async def dispatch(self, operation, data):
        if operation == "state":
            state = await super().dispatch(operation, data)
            return {**state, "selected_chat": self.selected_chat, "history": self.displayed_messages}
        if operation in {"select", "select_sender", "clear_target"}:
            self.idle_only()
            if operation == "clear_target":
                self.clear_target()
                self.notify("idle", "Таргет сброшен. Нажми на сообщение нужного автора")
                return {}
            if operation == "select":
                self.clear_target()
                self.displayed_messages = []
                self.selected_chat = next((chat for chat in self.chat_list
                                           if chat["id"] == int(data["id"])), None)
                if self.selected_chat is None:
                    raise AIError("Чат не найден; обнови список")
                self.displayed_messages = await self.telegram.history(self.selected_chat["id"])
                self.notify("idle", "История загружена. Выбери таргета нажатием на его сообщение")
                return self.displayed_messages
            if self.selected_chat is None or not self.selected_chat["can_reply"]:
                raise AIError("В этом чате выбор таргета недоступен. Поддерживаются личные чаты и обычные группы")
            message = next((row for row in self.displayed_messages
                            if row["id"] == int(data["message_id"])), None)
            if not message or not message["can_target"]:
                raise AIError("Выбери сообщение человека, не своё, не бота и не анонимного автора")
            self.prepared = False
            self.target = {**self.selected_chat, "sender_id": message["sender_id"],
                           "sender_name": message["sender_name"]}
            self.telegram.target_sender = message["sender_id"]
            self.notify("idle", "Таргет: " + message["sender_name"] + ". Модель читает только его сообщения")
            return self.target
        if operation == "prepare" and data.get("mode", "ai") == "ai":
            if not self.target or self.telegram.target_sender != self.target.get("sender_id"):
                self.prepared = False
                raise AIError("Выбери таргета: загрузи чат и нажми на сообщение нужного автора")
        if operation == "logout":
            result = await super().dispatch(operation, data)
            self.selected_chat, self.displayed_messages = None, []
            return result
        return await super().dispatch(operation, data)
