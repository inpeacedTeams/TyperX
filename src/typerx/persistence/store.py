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
        if not self.state_path.exists():
            return AppState(templates=[], selected_template_id="")
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            profile_data = dict(raw.get("profile", {}))
            if int(raw.get("schema_version", 1)) < 2:
                profile_data["typo_rate"] = min(
                    40.0,
                    float(profile_data.get("typo_rate", 1.2)) * 10,
                )
            profile = TypingProfile(**profile_data).normalized()
            templates = [
                TextTemplate.from_dict(item)
                for item in raw.get("templates", [])
                if not item.get("builtin")
            ]
            selected = str(raw.get("selected_template_id", ""))
            if selected not in {item.id for item in templates}:
                selected = templates[0].id if templates else ""
            return AppState(
                profile=profile,
                templates=templates,
                selected_template_id=selected,
                window_width=max(1040, int(raw.get("window_width", 1240))),
                window_height=max(680, int(raw.get("window_height", 780))),
            )
        except (OSError, ValueError, TypeError):
            backup = self.state_path.with_suffix(".broken.json")
            shutil.copy2(self.state_path, backup)
            return AppState(templates=[], selected_template_id="")

    def save(self, state: AppState) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = state.to_dict()
        payload["templates"] = [
            template_dict(item) for item in state.templates if not item.builtin
        ]
        descriptor, temporary = tempfile.mkstemp(
            prefix="state-",
            suffix=".json",
            dir=self.data_dir,
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
