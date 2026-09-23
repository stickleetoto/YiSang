import json

from yisang.ego.package import discover_ego_packages, load_ego_package
from yisang.ego.registry import EgoRegistry
from yisang.identity.snapshot import ego_registry_digest


def _package(root):
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps({
            "schema_version": 2,
            "ego_id": "ego.stable",
            "version": "1.0.0",
            "name": "Stable",
            "description": "Stable progressive package",
            "provides": ["stable.cap"],
            "instructions_file": "SKILL.md"
        }),
        encoding="utf-8",
    )
    (root / "SKILL.md").write_text("full instructions", encoding="utf-8")


def test_v2_registry_digest_is_stable_across_progressive_activation(tmp_path):
    package = tmp_path / "ego"
    _package(package)
    metadata = discover_ego_packages(tmp_path)[0].summary
    full = load_ego_package(package)

    metadata_registry = EgoRegistry()
    metadata_registry.register(metadata)
    full_registry = EgoRegistry()
    full_registry.register(full)

    assert metadata.package_digest == full.package_digest
    assert ego_registry_digest(metadata_registry) == ego_registry_digest(full_registry)
