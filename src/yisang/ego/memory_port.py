from __future__ import annotations

from dataclasses import replace
import time

from .package import semantic_version_key
from .port import EgoPort, InstalledEgoPackage


class InMemoryEgoPort(EgoPort):
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], InstalledEgoPackage] = {}

    def install(
        self,
        package: InstalledEgoPackage,
        *,
        supersede_active: bool = True,
    ) -> InstalledEgoPackage:
        key = (package.ego_id, package.version)
        if key in self._items:
            raise ValueError(
                f"duplicate E.G.O install: {package.ego_id}@{package.version}"
            )
        now = time.time()
        if supersede_active:
            for old_key, old in tuple(self._items.items()):
                if old.ego_id == package.ego_id and old.active:
                    self._items[old_key] = replace(
                        old,
                        state="superseded",
                        superseded_by_version=package.version,
                        status_reason=f"superseded by {package.version}",
                        updated_at=now,
                    )
        installed = replace(
            package,
            state="active",
            superseded_by_version=None,
            updated_at=now,
        )
        self._items[key] = installed
        return installed

    def get(
        self,
        ego_id: str,
        version: str | None = None,
    ) -> InstalledEgoPackage | None:
        if version is not None:
            return self._items.get((ego_id, version))
        active = [
            item for item in self._items.values()
            if item.ego_id == ego_id and item.active
        ]
        if active:
            return max(active, key=lambda item: semantic_version_key(item.version))
        versions = self.list_versions(ego_id)
        return versions[-1] if versions else None

    def list_versions(self, ego_id: str) -> tuple[InstalledEgoPackage, ...]:
        return tuple(
            sorted(
                (
                    item for item in self._items.values()
                    if item.ego_id == ego_id
                ),
                key=lambda item: semantic_version_key(item.version),
            )
        )

    def list_active(self) -> tuple[InstalledEgoPackage, ...]:
        return tuple(
            sorted(
                (item for item in self._items.values() if item.active),
                key=lambda item: (item.ego_id, semantic_version_key(item.version)),
            )
        )

    def disable(
        self,
        ego_id: str,
        version: str,
        *,
        reason: str,
    ) -> InstalledEgoPackage:
        key = (ego_id, version)
        current = self._items.get(key)
        if current is None:
            raise KeyError(f"{ego_id}@{version}")
        if not reason.strip():
            raise ValueError("reason must be non-empty")
        updated = replace(
            current,
            state="disabled",
            superseded_by_version=None,
            status_reason=reason.strip(),
            updated_at=time.time(),
        )
        self._items[key] = updated
        return updated

    def rollback(
        self,
        ego_id: str,
        to_version: str,
        *,
        reason: str,
    ) -> InstalledEgoPackage:
        if not reason.strip():
            raise ValueError("reason must be non-empty")
        target_key = (ego_id, to_version)
        target = self._items.get(target_key)
        if target is None:
            raise KeyError(f"{ego_id}@{to_version}")
        now = time.time()
        for key, item in tuple(self._items.items()):
            if item.ego_id == ego_id and item.active and key != target_key:
                self._items[key] = replace(
                    item,
                    state="superseded",
                    superseded_by_version=to_version,
                    status_reason=f"rollback: {reason.strip()}",
                    updated_at=now,
                )
        restored = replace(
            target,
            state="active",
            superseded_by_version=None,
            status_reason=f"rollback target: {reason.strip()}",
            updated_at=now,
        )
        self._items[target_key] = restored
        return restored
