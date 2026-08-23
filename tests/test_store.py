import json
from pathlib import Path

from typerx.persistence.store import AppStore, new_template


def test_fresh_store_starts_without_templates(tmp_path: Path) -> None:
    state = AppStore(tmp_path).load()
    assert state.templates == []
    assert state.selected_template_id == ""


def test_store_round_trip(tmp_path: Path) -> None:
    store = AppStore(tmp_path)
    state = store.load()
    template = new_template("Mine", "hello")
    state.templates.append(template)
    state.selected_template_id = template.id
    store.save(state)
    loaded = store.load()
    assert any(x.title == "Mine" and x.text == "hello" for x in loaded.templates)
    assert loaded.selected_template_id == template.id
    json.loads(store.state_path.read_text(encoding="utf-8"))


def test_broken_state_recovers_to_empty_library(tmp_path: Path) -> None:
    store = AppStore(tmp_path)
    store.state_path.write_text("not json", encoding="utf-8")
    state = store.load()
    assert state.templates == []
    assert state.selected_template_id == ""
    assert store.state_path.with_suffix(".broken.json").exists()


def test_obsolete_builtin_templates_are_not_restored(tmp_path: Path) -> None:
    store = AppStore(tmp_path)
    store.state_path.write_text(
        json.dumps(
            {
                "schema_version": 5,
                "templates": [
                    {
                        "id": "warmup",
                        "title": "Разогрев",
                        "text": "old",
                        "builtin": True,
                    }
                ],
                "selected_template_id": "warmup",
            }
        ),
        encoding="utf-8",
    )
    state = store.load()
    assert state.templates == []
    assert state.selected_template_id == ""
