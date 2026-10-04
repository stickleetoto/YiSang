from yisang.ego.package import EgoPackageDescriptor
from yisang.ego.versioned_registry import VersionedEgoRegistry

from test_ego_v2_package import _write_package


def test_versioned_registry_selects_latest_without_loading_details(tmp_path):
    _write_package(tmp_path / "v1", version="1.0.0")
    _write_package(tmp_path / "v2", version="1.2.0")

    registry = VersionedEgoRegistry()
    assert registry.discover_directory(tmp_path) == 2

    metadata = registry.get_metadata("ego.python.debug")
    assert metadata.version == "1.2.0"
    assert metadata.detail_level == "metadata"
    assert metadata.instructions == ""
    assert registry.list_versions("ego.python.debug") == ("1.0.0", "1.2.0")


def test_versioned_registry_activates_only_selected_package(tmp_path):
    _write_package(tmp_path / "v1", version="1.0.0")
    _write_package(tmp_path / "v2", version="1.2.0")

    registry = VersionedEgoRegistry()
    registry.discover_directory(tmp_path)

    loaded = registry.activate("ego.python.debug", "1.0.0")
    untouched = registry.get_metadata("ego.python.debug", "1.2.0")

    assert loaded.detail_level == "full"
    assert loaded.version == "1.0.0"
    assert untouched.detail_level == "metadata"
