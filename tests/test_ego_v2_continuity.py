from yisang.ego.models import EgoManifest
from yisang.ego.registry import EgoRegistry
from yisang.identity.snapshot import ego_registry_digest


def _v2(version):
    return EgoManifest(
        ego_id="ego.v2",
        name="V2",
        provides=("cap",),
        schema_version=2,
        version=version,
        description="versioned capability",
        tags=("capability",),
        package_digest="sha256:" + ("a" * 64),
    )


def test_v2_metadata_changes_ego_registry_digest():
    first = EgoRegistry()
    first.register(_v2("1.0.0"))
    second = EgoRegistry()
    second.register(_v2("1.1.0"))

    assert ego_registry_digest(first) != ego_registry_digest(second)
