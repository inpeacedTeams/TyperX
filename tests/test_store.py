import json
from pathlib import Path

from typerx.persistence.store import AppStore, new_template


def test_store_round_trip(tmp_path: Path) -> None:
    store = AppStore(tmp_path)
    state = store.load()
    state.templates.append(new_template("Mine", "hello"))
    store.save(state)
    loaded = store.load()
    assert any(x.title == "Mine" and x.text == "hello" for x in loaded.templates)
    json.loads(store.state_path.read_text(encoding="utf-8"))


def test_broken_state_recovers(tmp_path: Path) -> None:
    store = AppStore(tmp_path)
    store.state_path.write_text("not json", encoding="utf-8")
    assert store.load().templates
    assert store.state_path.with_suffix(".broken.json").exists()
