from __future__ import annotations

import json
from pathlib import Path

from .models import EgoManifest

def load_ego_directory(root: str | Path) -> list[EgoManifest]:
    root_path = Path(root)
    if not root_path.exists():
        raise FileNotFoundError(root_path)

    manifests: list[EgoManifest] = []
    for manifest_path in sorted(root_path.rglob("manifest.json")):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        skill_path = manifest_path.with_name("SKILL.md")
        instructions = (
            skill_path.read_text(encoding="utf-8").strip()
            if skill_path.exists()
            else ""
        )

        manifests.append(
            EgoManifest(
                ego_id=_required_string(data, "ego_id", manifest_path),
                name=_required_string(data, "name", manifest_path),
                provides=tuple(_string_list(data.get("provides", []), "provides", manifest_path)),
                keywords=tuple(_string_list(data.get("keywords", []), "keywords", manifest_path)),
                instructions=instructions,
                permissions=dict(data.get("permissions", {})),
            )
        )
    return manifests

def _required_string(data: dict, key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: {key} must be a non-empty string")
    return value.strip()

def _string_list(value, key: str, path: Path) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{path}: {key} must be a list of strings")
    return [item for item in value if item]
