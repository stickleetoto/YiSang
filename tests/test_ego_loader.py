import json
from yisang.ego.registry import EgoRegistry

def test_loads_ego_from_directory(tmp_path):
    ego = tmp_path / "ego" / "debug"
    ego.mkdir(parents=True)
    (ego / "manifest.json").write_text(json.dumps({
        "ego_id": "ego.debug",
        "name": "Debugger",
        "provides": ["debug"],
        "keywords": ["bug"],
        "permissions": {"filesystem": "read"},
    }), encoding="utf-8")
    (ego / "SKILL.md").write_text("Verify before claiming success.", encoding="utf-8")

    registry = EgoRegistry.from_directory(tmp_path / "ego")
    loaded = registry.get("ego.debug")
    assert loaded.name == "Debugger"
    assert "Verify before" in loaded.instructions

def test_rejects_invalid_manifest(tmp_path):
    ego = tmp_path / "ego" / "bad"
    ego.mkdir(parents=True)
    (ego / "manifest.json").write_text('{"name":"Missing ID"}', encoding="utf-8")

    try:
        EgoRegistry.from_directory(tmp_path / "ego")
    except ValueError as exc:
        assert "ego_id" in str(exc)
    else:
        raise AssertionError("invalid manifest was accepted")
