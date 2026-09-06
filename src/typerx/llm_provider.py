"""Provider-aware HTTP diagnostics without exposing remote error text or credentials."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from typerx.ai import AIError, NoRedirect, OpenAIClient
from typerx.targeting import SenderRuntime


def explain_http_error(exc):
    status = exc.code
    try:
        raw = exc.read(16385)
        if len(raw) > 16384:
            raw = b""
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            value = {}
        error = value.get("error", {}) if isinstance(value, dict) else {}
        error = error if isinstance(error, dict) else {}
        # Only interpret known identifiers. Never display provider-controlled messages.
        code, kind = error.get("code"), error.get("type")
        html = ("text/html" in str(exc.headers.get("Content-Type", "")).lower()
                or raw.lstrip().lower().startswith((b"<!doctype html", b"<html")))
    except (OSError, ValueError, AttributeError):
        code, kind, html = None, None, False
    finally:
        exc.close()
    if status == 403:
        if code == "permission_denied" or kind == "permission_error":
            detail = ("Провайдер запретил доступ к выбранной модели. Проверь доступ модели для "
                      "аккаунта/ключа и тариф в кабинете провайдера либо выбери доступную модель. "
                      "Суффикс :free сам по себе не гарантирует доступ. Повтор без изменения доступа не поможет.")
        elif html:
            detail = ("Вместо ответа API получена HTML-страница отказа. Возможна блокировка "
                      "сетевым фильтром, прокси или защитой сервера. Проверь доступность API "
                      "из этой сети и обратись к провайдеру; это не подтверждает ошибку ключа.")
        else:
            detail = ("Доступ запрещён сервером. Проверь права ключа, доступ к модели и "
                      "ограничения сети в кабинете провайдера. По одному HTTP 403 точную причину определить нельзя.")
    else:
        detail = {
            400: "Провайдер отклонил параметры или содержимое запроса. Проверь поддержку chat/completions выбранной моделью.",
            401: "Ключ не принят. Введи действующий API-ключ именно этого провайдера и сохрани настройки.",
            402: "Недостаточно баланса или квоты. Проверь биллинг у провайдера.",
            404: "Модель или endpoint не найдены. Проверь точный ID модели и base URL, включая /v1, если он нужен провайдеру.",
            422: "Провайдер не принимает формат запроса для этой модели.",
            429: "Достигнут лимит запросов или использования. Проверь квоту и повтори позже.",
        }.get(status, "Ошибка на стороне провайдера или промежуточного сервера. Проверь состояние сервиса.")
    return f"LLM: HTTP {status}. {detail}"


class ProviderClient(OpenAIClient):
    @staticmethod
    def _request(url, key, payload):
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                   "User-Agent": "TyperX/1.2 (+OpenAI-compatible desktop client)"}
        if key:
            headers["Authorization"] = "Bearer " + key
        request = urllib.request.Request(url, data=payload, headers=headers)
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=45) as response:
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise AIError("Ответ модели слишком большой")
            content = json.loads(raw)["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise AIError("Модель вернула пустой ответ")
            if len(content) > 8000:
                raise AIError("Ответ длиннее 8000 символов; сократи промпт")
            return re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", content).strip()
        except urllib.error.HTTPError as exc:
            raise AIError(explain_http_error(exc)) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise AIError("LLM недоступен или не ответил за 45 секунд") from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise AIError("Нужен OpenAI-совместимый ответ chat/completions") from None


class ProviderRuntime(SenderRuntime):
    def __init__(self, root, emit):
        super().__init__(root, emit)
        self.llm = ProviderClient()
