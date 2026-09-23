from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import EgoManifest
from .package import (
    EgoPackageDescriptor,
    discover_ego_packages,
    semantic_version_key,
)


@dataclass(frozen=True)
class InstalledEgoVersion:
    ego_id: str
    version: str
    metadata: EgoManifest
    descriptor: EgoPackageDescriptor | None = None


class VersionedEgoRegistry:
    """Version-aware E.G.O package registry with lazy package activation."""

    def __init__(self) -> None:
        self._items: dict[str, dict[str, InstalledEgoVersion]] = {}
        self._loaded: dict[tuple[str, str], EgoManifest] = {}

    def register_manifest(self, manifest: EgoManifest) -> None:
        self._register(
            InstalledEgoVersion(
                ego_id=manifest.ego_id,
                version=manifest.version,
                metadata=manifest,
                descriptor=None,
            )
        )
        if manifest.is_fully_loaded:
            self._loaded[(manifest.ego_id, manifest.version)] = manifest

    def discover_directory(self, root: str | Path) -> int:
        count = 0
        for descriptor in discover_ego_packages(root):
            self._register(
                InstalledEgoVersion(
                    ego_id=descriptor.summary.ego_id,
                    version=descriptor.summary.version,
                    metadata=descriptor.summary,
                    descriptor=descriptor,
                )
            )
            count += 1
        return count

    def list_all(self) -> list[EgoManifest]:
        return [
            self.get_metadata(ego_id)
            for ego_id in sorted(self._items)
        ]

    def list_versions(self, ego_id: str) -> tuple[str, ...]:
        versions = self._items.get(ego_id)
        if not versions:
            return ()
        return tuple(
            sorted(versions, key=semantic_version_key)
        )

    def get_metadata(
        self,
        ego_id: str,
        version: str | None = None,
    ) -> EgoManifest:
        item = self._select(ego_id, version)
        return item.metadata

    def activate(
        self,
        ego_id: str,
        version: str | None = None,
    ) -> EgoManifest:
        item = self._select(ego_id, version)
        key = (item.ego_id, item.version)
        cached = self._loaded.get(key)
        if cached is not None:
            return cached
        if item.descriptor is None:
            loaded = item.metadata
        else:
            loaded = item.descriptor.load()
        self._loaded[key] = loaded
        return loaded

    def _register(self, item: InstalledEgoVersion) -> None:
        versions = self._items.setdefault(item.ego_id, {})
        if item.version in versions:
            raise ValueError(
                f"duplicate E.G.O version: {item.ego_id}@{item.version}"
            )
        semantic_version_key(item.version)
        versions[item.version] = item

    def _select(
        self,
        ego_id: str,
        version: str | None,
    ) -> InstalledEgoVersion:
        versions = self._items.get(ego_id)
        if not versions:
            raise KeyError(ego_id)
        selected = version or max(versions, key=semantic_version_key)
        try:
            return versions[selected]
        except KeyError as exc:
            raise KeyError(f"{ego_id}@{selected}") from exc
