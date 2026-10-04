import json

import pytest

from yisang.ego.a2a import ego_to_a2a_skill
from yisang.ego.models import JSON_SCHEMA_2020_12
from yisang.ego.package import (
    discover_ego_packages,
    load_ego_package,
)


def _write_package(root, *, version="1.2.0", resource_text="pytest notes"):
    root.mkdir(parents=True)
    manifest = {
        "schema_version": 2,
        "ego_id": "ego.python.debug",
        "version": version,
        "name": "Python Debugger",
        "description": "Diagnose and repair Python pytest failures.",
        "provides": ["python.debug", "python.test.repair"],
        "keywords": ["python", "pytest"],
        "tags": ["debugging", "testing"],
        "examples": ["pytest가 실패해", "fix this Python traceback"],
        "requires": ["filesystem.read"],
        "conflicts": [],
        "permissions": {"filesystem.read": True, "filesystem.write": "workspace"},
        "risk": {
            "read_only": False,
            "destructive": False,
            "idempotent": False,
            "open_world": False,
        },
        "runtime": {"type": "native"},
        "instructions_file": "SKILL.md",
        "input_schema_file": "schemas/input.json",
        "output_schema_file": "schemas/output.json",
        "resources": ["references/pytest.md"],
        "evals": ["evals/basic.json"],
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    (root / "SKILL.md").write_text(
        "Verify the failure before changing code.",
        encoding="utf-8",
    )
    (root / "schemas").mkdir()
    schema = {"$schema": JSON_SCHEMA_2020_12, "type": "object"}
    (root / "schemas" / "input.json").write_text(json.dumps(schema), encoding="utf-8")
    (root / "schemas" / "output.json").write_text(json.dumps(schema), encoding="utf-8")
    (root / "references").mkdir()
    (root / "references" / "pytest.md").write_text(resource_text, encoding="utf-8")
    (root / "evals").mkdir()
    (root / "evals" / "basic.json").write_text("{}", encoding="utf-8")


def test_progressive_discovery_loads_metadata_only(tmp_path):
    package = tmp_path / "python-debug"
    _write_package(package)

    descriptors = discover_ego_packages(tmp_path)

    assert len(descriptors) == 1
    summary = descriptors[0].summary
    assert summary.detail_level == "metadata"
    assert summary.instructions == ""
    assert summary.description.startswith("Diagnose")
    assert summary.version == "1.2.0"


def test_full_package_loads_instructions_schemas_and_digest(tmp_path):
    package = tmp_path / "python-debug"
    _write_package(package)

    loaded = load_ego_package(package)

    assert loaded.detail_level == "full"
    assert "Verify the failure" in loaded.instructions
    assert loaded.input_schema["type"] == "object"
    assert loaded.output_schema["$schema"] == JSON_SCHEMA_2020_12
    assert loaded.package_digest.startswith("sha256:")
    assert len(loaded.package_digest) == 71


def test_package_digest_changes_when_resource_changes(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write_package(first, resource_text="A")
    _write_package(second, resource_text="B")

    assert load_ego_package(first).package_digest != load_ego_package(second).package_digest


def test_rejects_package_path_traversal(tmp_path):
    package = tmp_path / "bad"
    package.mkdir()
    manifest = {
        "schema_version": 2,
        "ego_id": "ego.bad",
        "version": "1.0.0",
        "name": "Bad",
        "description": "Bad package",
        "provides": [],
        "instructions_file": "../escape.md",
    }
    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="escape root"):
        discover_ego_packages(tmp_path)


def test_a2a_export_uses_discovery_metadata(tmp_path):
    package = tmp_path / "python-debug"
    _write_package(package)
    summary = discover_ego_packages(tmp_path)[0].summary

    skill = ego_to_a2a_skill(summary)

    assert skill["id"] == "ego.python.debug"
    assert skill["description"] == summary.description
    assert "debugging" in skill["tags"]
    assert skill["examples"]
