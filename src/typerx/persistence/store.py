from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from typerx.domain.models import AppState, TextTemplate, TypingProfile


class AppStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.state_path = data_dir / "state.json"

    @classmethod
    def default(cls) -> "AppStore":
        root = Path(os.environ.get("APPDATA", Path.home())) / "TyperX"
        return cls(root)

    def load(self) -> AppState:
        builtins = builtin_templates()
        if not self.state_path.exists():
            return AppState(templates=builtins, selected_template_id=builtins[0].id)
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            profile = TypingProfile(**raw.get("profile", {})).normalized()
            custom = [
                TextTemplate.from_dict(item)
                for item in raw.get("templates", [])
                if not item.get("builtin")
            ]
            return AppState(
                profile=profile,
                templates=builtins + custom,
                selected_template_id=str(raw.get("selected_template_id", "")),
                window_width=max(1040, int(raw.get("window_width", 1240))),
                window_height=max(680, int(raw.get("window_height", 780))),
            )
        except (OSError, ValueError, TypeError):
            backup = self.state_path.with_suffix(".broken.json")
            shutil.copy2(self.state_path, backup)
            return AppState(templates=builtins, selected_template_id=builtins[0].id)

    def save(self, state: AppState) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = state.to_dict()
        payload["templates"] = [
            template_dict(item) for item in state.templates if not item.builtin
        ]
        descriptor, temporary = tempfile.mkstemp(
            prefix="state-", suffix=".json", dir=self.data_dir
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.state_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def template_dict(item: TextTemplate) -> dict[str, object]:
    return {
        "id": item.id,
        "title": item.title,
        "text": item.text,
        "category": item.category,
        "builtin": item.builtin,
    }


def new_template(title: str = "Новый шаблон", text: str = "") -> TextTemplate:
    return TextTemplate(id=str(uuid.uuid4()), title=title, text=text)


def builtin_templates() -> list[TextTemplate]:
    rows = [
        ("warmup", "Разогрев", "Привет как дела что делаешь чем занимаешься я например учу уроки."),
        ("cosmos", "Космический эксперт", "Ты сейчас так уверенно это написал будто лично согласовывал законы физики с советом галактики. Подожди я записываю эту историческую мысль."),
        ("support", "Техподдержка", "Проверил твою аргументацию. Перезагрузка не помогла. Попробуй выключить уверенность на десять секунд и включить факты."),
        ("archive", "Архив интернета", "Не удаляй сообщение пожалуйста. Интернет должен сохранить этот момент для будущих исследователей. Они будут спорить что именно ты имел в виду."),
        ("news", "Срочные новости", "Срочные новости. В чате обнаружено мнение такой плотности что рядом перестал работать компас. Специалисты уже выехали."),
        ("museum", "Музейный экспонат", "Эту переписку нельзя заканчивать. Её надо аккуратно поместить под стекло. Табличка будет называться человек был уверен до самого конца."),
        ("director", "Режиссёрская версия", "Постой это была полная версия мысли или только трейлер. Интрига есть сюжет потерялся а продолжение почему-то уже пугает."),
        ("chess", "Шахматы 5D", "Ход неожиданный. Настолько неожиданный что даже ты похоже не понял куда пошла фигура. Но уверенность конечно чемпионская."),
        ("office", "Финальный босс", "С таким серьёзным тоном обычно объявляют квартальный отчёт. А тут одна фраза и уже ощущение будто началась последняя битва с бухгалтерией."),
        ("final", "Спокойный финал", "Ладно убедил. Не аргументами конечно а выносливостью. Я просто не был готов что эта мысль будет возвращаться каждый сезон."),
    ]
    return [
        TextTemplate(id=item_id, title=title, text=text, category="Ирония", builtin=True)
        for item_id, title, text in rows
    ]
