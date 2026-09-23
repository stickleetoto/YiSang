from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .a2a import ego_to_a2a_skill
from .package import JSON_SCHEMA_2020_12
from .router_v2 import HybridCapabilityRouter
from .versioned_registry import VersionedEgoRegistry


def _write_package(root: Path, *, version: str, label: str) -> None:
    root.mkdir(parents=True)
    manifest = {
        "schema_version": 2,
        "ego_id": "ego.python.debug",
        "version": version,
        "name": "Python Debugger",
        "description": "Diagnose Python pytest failures and tracebacks.",
        "provides": ["python.debug", "python.test.repair"],
        "keywords": ["python", "pytest"],
        "tags": ["debugging", "testing"],
        "examples": ["pytest failure", "Python traceback"],
        "requires": ["filesystem.read"],
        "conflicts": [],
        "permissions": {
            "filesystem.read": True,
            "filesystem.write": "workspace"
        },
        "risk": {
            "read_only": False,
            "destructive": False,
            "idempotent": False,
            "open_world": False
        },
        "runtime": {"type": "native"},
        "instructions_file": "SKILL.md",
        "input_schema_file": "schemas/input.json",
        "output_schema_file": "schemas/output.json",
        "resources": ["references/pytest.md"],
        "evals": ["evals/basic.json"]
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    (root / "SKILL.md").write_text(
        f"{label}: verify before editing.",
        encoding="utf-8",
    )
    (root / "schemas").mkdir()
    schema = {"$schema": JSON_SCHEMA_2020_12, "type": "object"}
    (root / "schemas" / "input.json").write_text(
        json.dumps(schema),
        encoding="utf-8",
    )
    (root / "schemas" / "output.json").write_text(
        json.dumps(schema),
        encoding="utf-8",
    )
    (root / "references").mkdir()
    (root / "references" / "pytest.md").write_text(
        "pytest reference",
        encoding="utf-8",
    )
    (root / "evals").mkdir()
    (root / "evals" / "basic.json").write_text("{}", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yisang-ego-v2-smoke")
    parser.parse_args(argv)

    with TemporaryDirectory(prefix="yisang-ego-v2-") as temp:
        root = Path(temp)
        _write_package(root / "v1", version="1.0.0", label="old")
        _write_package(root / "v2", version="1.2.0", label="new")

        registry = VersionedEgoRegistry()
        discovered = registry.discover_directory(root)
        summaries = registry.list_all()
        selected = HybridCapabilityRouter().route(
            "python pytest traceback",
            summaries,
            required_capabilities=("python.debug",),
            limit=1,
        )
        summary = selected[0]
        loaded = registry.activate(summary.ego_id, summary.version)
        skill = ego_to_a2a_skill(summary)

        payload = {
            "ready": bool(
                discovered == 2
                and summary.version == "1.2.0"
                and summary.detail_level == "metadata"
                and summary.instructions == ""
                and summary.package_digest is not None
                and loaded.detail_level == "full"
                and "new: verify before editing." in loaded.instructions
                and loaded.package_digest == summary.package_digest
                and skill["id"] == "ego.python.debug"
            ),
            "discovered_versions": list(
                registry.list_versions("ego.python.debug")
            ),
            "selected_version": summary.version,
            "metadata_only_before_activation": summary.instructions == "",
            "package_digest_bound_before_activation": (
                summary.package_digest is not None
            ),
            "full_loaded_after_activation": loaded.is_fully_loaded,
            "digest_stable_across_activation": (
                loaded.package_digest == summary.package_digest
            ),
            "a2a_skill_id": skill["id"],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
