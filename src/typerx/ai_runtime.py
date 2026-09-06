"""Desktop orchestration. Only TypingService is allowed to produce output."""
from __future__ import annotations

import asyncio
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from typerx.ai import AIError, AIStore, OpenAIClient, ReplyLoop, TelegramGateway


def initialize_uia_thread():
    import pythoncom
    pythoncom.CoInitialize()


def focused_editor():
    # All UIA calls use one dedicated COM-initialized thread.
    from pywinauto.uia_defines import IUIA
    from pywinauto.uia_element_info import UIAElementInfo
    from pywinauto.controls.uia_controls import EditWrapper
    element = IUIA().iuia.GetFocusedElement()
    if element.CurrentControlType != 50004:
        raise AIError("Поставь курсор в поле сообщения")
    editor = EditWrapper(UIAElementInfo(element))
    return tuple(element.GetRuntimeId() or ()), editor.get_value()


class TargetGuard:
    """Fail closed if Telegram does not expose the selected peer in its window title.

    A HWND alone cannot identify a chat. Generic 'Telegram' windows are rejected.
    This is a GUI safety check, not a cryptographic mapping to a Telegram peer ID.
    """
    def __init__(self, peer_name=None):
        import win32api
        import win32gui
        import win32process
        self.hwnd = win32gui.GetForegroundWindow()
        self.title = win32gui.GetWindowText(self.hwnd)
        self.peer_name = peer_name
        if peer_name:
            _, pid = win32process.GetWindowThreadProcessId(self.hwnd)
            handle = win32api.OpenProcess(0x1000, False, pid)
            try:
                import ctypes
                from ctypes import wintypes
                query = ctypes.windll.kernel32.QueryFullProcessImageNameW
                query.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                  ctypes.POINTER(wintypes.DWORD)]
                query.restype = wintypes.BOOL
                size = wintypes.DWORD(32768)
                buffer = ctypes.create_unicode_buffer(size.value)
                if not query(int(handle), 0, buffer, ctypes.byref(size)):
                    raise AIError("Не удалось проверить процесс Telegram")
                if buffer.value.replace("\\", "/").rsplit("/", 1)[-1].lower() != "telegram.exe":
                    raise AIError("Открой Telegram Desktop и нажми F8 в поле сообщения")
            finally:
                win32api.CloseHandle(handle)
            title = re.sub(r"^\(\d+\)\s*", "", self.title).strip()
            allowed = {peer_name, peer_name + " – Telegram", peer_name + " — Telegram",
                       peer_name + " - Telegram", peer_name + " - Telegram Desktop"}
            if title not in allowed:
                raise AIError("Заголовок окна должен содержать только имя выбранного чата "
                              "(допустим суффикс Telegram). Открой отдельное окно чата. "
                              "Окно с общим заголовком Telegram небезопасно")
            self.focus_id, value = focused_editor()
            if value.strip():
                raise AIError("Поле сообщения должно быть пустым перед запуском")
            if not self.focus_id:
                raise AIError("Telegram не предоставил идентификатор поля ввода")
        self.check()

    def check(self):
        import win32gui
        if (win32gui.GetForegroundWindow() != self.hwnd
                or win32gui.GetWindowText(self.hwnd) != self.title):
            raise AIError("Окно или чат изменились. Ввод остановлен; очисти черновик перед перезапуском")

    def check_field(self, empty=False):
        self.check()
        if self.peer_name:
            focus_id, value = focused_editor()
            if focus_id != self.focus_id:
                raise AIError("Фокус поля сообщения изменился. Цикл остановлен")
            if empty and value.strip():
                raise AIError("В поле сообщения уже есть черновик. Цикл остановлен")


def driver_output(text, config, guard, stopped, notify):
    from typerx.domain.models import TypingProfile
    from typerx.domain.splitter import SmartSplitter
    from typerx.platform.interception_keyboard import InterceptionKeyboard
    from typerx.services.typing_service import TypingCancelled, TypingService

    class GuardedTyping(TypingService):
        def _check(self):
            if stopped.is_set():
                raise TypingCancelled
            guard.check()
            super()._check()

        def _wait(self, duration):
            deadline = time.monotonic() + duration
            while True:
                self._check()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                if stopped.wait(min(0.025, remaining)):
                    raise TypingCancelled

    if stopped.is_set():
        raise TypingCancelled
    guard.check()
    # Driver-only output cannot type arbitrary Unicode. Validate before the first keystroke.
    text = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
    text = text.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'",
                                       "—": "-", "–": "-", "…": "...", "\u00a0": " "}))
    keyboard = InterceptionKeyboard(guard.hwnd)
    try:
        for char in sorted(set(text)):
            if stopped.is_set():
                raise TypingCancelled
            guard.check()
            keyboard._resolve_char(char)
    finally:
        keyboard.close()
    profile = TypingProfile(wpm=config["wpm"], words_per_message=config["words"],
                            typo_rate=1.2, auto_123_challenge=False)
    plan = SmartSplitter().plan(text, profile)
    service = GuardedTyping()
    service.run(plan, profile, guard.hwnd,
                lambda current, total: notify("typing", f"Печать сообщения {current} из {total}"))


class Runtime:
    def __init__(self, root, emit):
        self.emit = emit
        self.store = AIStore(root)
        self.telegram = TelegramGateway(self.store, self.notify)
        self.llm = OpenAIClient()
        self.closed = threading.Event()
        self.stopped = threading.Event()
        self.stopped.set()
        self.ui_executor = ThreadPoolExecutor(max_workers=1, initializer=initialize_uia_thread)
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.request_lock = asyncio.Lock()
        self.epoch = 0
        self.control_lock = threading.Lock()
        self.own_window = 0
        self.job = None
        self.writer = None
        self.guard = None
        self.mode = "ai"
        self.prepared = False
        self.target = None
        self.chat_list = []
        self.manual_text = ""
        self.stage = "idle"
        self.detail = "Подключи аккаунт и выбери собеседника"

    def notify(self, stage, detail):
        self.stage, self.detail = stage, detail
        self.emit({"event": "state", "stage": stage, "detail": detail,
                   "prepared": self.prepared, "active": bool(self.job and not self.job.done())})

    def stop(self):
        # Called directly by F9, not queued behind an LLM or Telegram request.
        with self.control_lock:
            self.epoch += 1
            self.stopped.set()
        if not self.loop.is_closed():
            self.loop.call_soon_threadsafe(self._cancel)

    def _cancel(self):
        self.prepared = False
        if self.job and not self.job.done():
            if not self.job.cancelling():
                self.job.cancel()
        else:
            self.notify("idle", "Остановлено · F9")

    def submit(self, request_id, operation, data):
        if self.closed.is_set():
            return
        with self.control_lock:
            epoch = self.epoch
        asyncio.run_coroutine_threadsafe(self._request(request_id, operation, data, epoch), self.loop)

    async def _request(self, request_id, operation, data, epoch=None):
        try:
            async with self.request_lock:
                if operation == "start" and epoch is not None and epoch != self.epoch:
                    raise AIError("Отложенный запуск отменён через F9")
                value = await self.dispatch(operation, data)
            self.emit({"id": request_id, "ok": True, "data": value})
        except asyncio.CancelledError:
            self.emit({"id": request_id, "ok": False, "error": "Операция отменена"})
        except Exception as exc:
            # Never echo network exception messages, tokens, passwords or request bodies.
            message = str(exc) if isinstance(exc, AIError) else friendly_error(exc)
            self.emit({"id": request_id, "ok": False, "error": message})

    def idle_only(self):
        if self.job and not self.job.done():
            raise AIError("Сначала останови цикл: F9")

    async def dispatch(self, operation, data):
        if operation == "state":
            return {"config": self.store.public(), "stage": self.stage,
                    "detail": self.detail, "chats": self.chat_list, "target": self.target}
        if operation == "stop":
            self.stop()
            return {}
        if operation == "start":
            self.idle_only()
            if not self.prepared:
                raise AIError("Сначала нажми «Подготовить запуск» в TyperX")
            if self.mode == "ai" and (not self.telegram.client or not self.telegram.client.is_connected()):
                raise AIError("Telegram отключён; загрузи чаты заново")
            epoch = self.epoch
            self.guard = await self.loop.run_in_executor(
                self.ui_executor, TargetGuard, self.target["name"] if self.mode == "ai" else None)
            if not self.guard.hwnd or self.guard.hwnd == self.own_window:
                raise AIError("Открой поле ввода в другом приложении и нажми F8")
            with self.control_lock:
                if epoch != self.epoch:
                    raise AIError("Запуск отменён через F9")
                self.stopped.clear()
                self.prepared = False
                self.job = asyncio.create_task(self._run())
            return {}
        self.idle_only()
        if operation == "save":
            # Session API identity cannot change while a connected client still uses old credentials.
            changed = (str(data.get("api_id", "")) != self.store.config["api_id"]
                       or str(data.get("phone", "")) != self.store.config["phone"]
                       or bool(data.get("api_hash")) or bool(data.get("clear_api_hash")))
            if changed and self.telegram.client:
                raise AIError("Сначала выйди из Telegram, затем меняй данные аккаунта")
            self.store.save(data)
            self.prepared = False
            return self.store.public()
        if operation == "code":
            return await self.telegram.request_code()
        if operation == "login":
            return await self.telegram.sign_in(str(data.get("code", "")), str(data.get("password", "")))
        if operation == "logout":
            await self.telegram.close(logout=True)
            self.target, self.chat_list, self.prepared = None, [], False
            return {}
        if operation == "chats":
            self.chat_list = await self.telegram.chats()
            return self.chat_list
        if operation == "select":
            self.prepared = False
            peer_id = int(data["id"])
            self.target = next((c for c in self.chat_list if c["id"] == peer_id), None)
            if not self.target:
                raise AIError("Чат не найден; обнови список")
            return await self.telegram.history(peer_id)
        if operation == "test":
            text = await self.llm.complete(self.store.config, self.store.secrets.get("api_key", ""), [], check=True)
            return {"message": "Подключение работает: " + text}
        if operation == "prepare":
            self.prepared = False
            self.mode = data.get("mode", "ai")
            if self.mode not in {"ai", "manual"}:
                raise AIError("Неизвестный режим")
            if self.mode == "ai":
                if not self.target or not self.target["can_reply"]:
                    raise AIError("Автоответ доступен только для личного чата с человеком")
                if sum(c["name"] == self.target["name"] for c in self.chat_list) != 1:
                    raise AIError("Есть чаты с одинаковыми именами; задай уникальное имя собеседнику")
                if not data.get("consent"):
                    raise AIError("Подтверди передачу истории выбранному LLM-провайдеру")
                if not self.store.config["model"]:
                    raise AIError("Укажи модель")
            else:
                self.manual_text = str(data.get("text", "")).strip()[:8000]
                if not self.manual_text:
                    raise AIError("Введи текст для печати")
            self.prepared = True
            self.notify("ready", "Открой пустое поле нужного чата и нажми F8")
            return {}
        raise AIError("Неизвестная операция")

    async def _output(self, text):
        if self.stopped.is_set():
            raise asyncio.CancelledError
        await self.loop.run_in_executor(self.ui_executor, lambda: self.guard.check_field(empty=True))
        self.writer = asyncio.create_task(asyncio.to_thread(
            driver_output, text, self.store.config, self.guard, self.stopped, self.notify))
        await asyncio.shield(self.writer)

    async def _monitor(self):
        while True:
            if self.stopped.is_set():
                raise AIError("Остановлено")
            await self.loop.run_in_executor(self.ui_executor, self.guard.check_field)
            if self.mode == "ai" and not self.telegram.client.is_connected():
                raise AIError("Telegram отключён. Переподключись и запусти цикл вручную")
            await asyncio.sleep(0.15)

    async def _run(self):
        tasks = []
        detail = "Остановлено. Проверь и очисти черновик перед новым запуском"
        stage = "idle"
        try:
            if self.mode == "ai":
                reply = ReplyLoop(self.telegram, self.llm, self._output, self.store, self.notify)
                self.telegram.target = self.target["id"]
                self.telegram.on_message = reply.incoming
                worker = asyncio.create_task(reply.run(self.target["id"]))
                self.notify("listening", "Ожидание нового сообщения")
            else:
                worker = asyncio.create_task(self._output(self.manual_text))
            monitor = asyncio.create_task(self._monitor())
            tasks = [worker, monitor]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
            detail = "Печать завершена"
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            stage = "error"
            detail = str(exc) if isinstance(exc, AIError) else friendly_error(exc)
        finally:
            self.stopped.set()
            self.telegram.target = self.telegram.on_message = None
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if self.writer:
                try:
                    await asyncio.shield(self.writer)
                except Exception:
                    pass
            self.prepared = False
            self.notify(stage, detail)

    def close(self):
        if self.closed.is_set():
            return
        self.closed.set()
        self.stop()
        async def shutdown():
            if self.job:
                await asyncio.gather(self.job, return_exceptions=True)
            await self.telegram.close()
            pending = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            await self.loop.shutdown_asyncgens()
        future = asyncio.run_coroutine_threadsafe(shutdown(), self.loop)
        try:
            future.result(timeout=8)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=2)
        self.ui_executor.shutdown(wait=False, cancel_futures=True)
        if not self.thread.is_alive():
            self.loop.close()


def friendly_error(exc):
    name = type(exc).__name__
    known = {
        "PhoneCodeInvalidError": "Неверный код Telegram",
        "PhoneCodeExpiredError": "Код истёк. Запроси новый",
        "PasswordHashInvalidError": "Неверный пароль 2FA",
        "PhoneNumberInvalidError": "Неверный номер телефона",
        "FloodWaitError": "Telegram ограничил попытки. Подожди перед повтором",
        "ApiIdInvalidError": "Неверные Telegram api_id / api_hash",
        "AuthKeyUnregisteredError": "Сессия Telegram отозвана; войди заново",
        "DriverNotReadyError": "Драйвер не готов или символ недоступен в раскладке. Проверь Interception и текст",
        "TypingCancelled": "Ввод остановлен; проверь черновик",
        "FocusChangedError": "Окно изменилось; ввод остановлен",
    }
    return known.get(name, "Операция не выполнена (" + name + "). Проверь подключение и настройки")
