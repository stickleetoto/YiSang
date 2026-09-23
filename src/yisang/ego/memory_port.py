from __future__ import annotations

from dataclasses import replace
import time
import uuid

from .package import semantic_version_key
from .port import (
    EgoAuditEvent,
    EgoInvalidationCandidate,
    EgoPort,
    InstalledEgoPackage,
)


class InMemoryEgoPort(EgoPort):
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], InstalledEgoPackage] = {}
        self._audit: list[EgoAuditEvent] = []
        self._invalidation: dict[str, EgoInvalidationCandidate] = {}

    def install(
        self,
        package: InstalledEgoPackage,
        *,
        supersede_active: bool = True,
        actor: str = "system",
        approval_ref: str | None = None,
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
                    self.record_audit(
                        _event(
                            "supersede",
                            old.ego_id,
                            old.version,
                            actor,
                            f"superseded by {package.version}",
                            approval_ref=approval_ref,
                            related_version=package.version,
                        )
                    )
        installed = replace(
            package,
            state="active",
            superseded_by_version=None,
            updated_at=now,
        )
        self._items[key] = installed
        self.record_audit(
            _event(
                "install",
                installed.ego_id,
                installed.version,
                actor,
                installed.status_reason or "installed E.G.O package",
                approval_ref=approval_ref or installed.approval_ref,
                metadata={
                    "source_artifact_id": installed.source_artifact_id,
                    "package_digest": installed.manifest.package_digest,
                },
            )
        )
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
        actor: str = "system",
        approval_ref: str | None = None,
    ) -> InstalledEgoPackage:
        key = (ego_id, version)
        current = self._items.get(key)
        if current is None:
            raise KeyError(f"{ego_id}@{version}")
        normalized = reason.strip()
        if not normalized:
            raise ValueError("reason must be non-empty")
        updated = replace(
            current,
            state="disabled",
            superseded_by_version=None,
            status_reason=normalized,
            updated_at=time.time(),
        )
        self._items[key] = updated
        self.record_audit(
            _event(
                "disable",
                ego_id,
                version,
                actor,
                normalized,
                approval_ref=approval_ref,
            )
        )
        return updated

    def rollback(
        self,
        ego_id: str,
        to_version: str,
        *,
        reason: str,
        actor: str = "system",
        approval_ref: str | None = None,
    ) -> InstalledEgoPackage:
        normalized = reason.strip()
        if not normalized:
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
                    status_reason=f"rollback: {normalized}",
                    updated_at=now,
                )
                self.record_audit(
                    _event(
                        "supersede",
                        item.ego_id,
                        item.version,
                        actor,
                        f"rollback: {normalized}",
                        approval_ref=approval_ref,
                        related_version=to_version,
                    )
                )
        restored = replace(
            target,
            state="active",
            superseded_by_version=None,
            status_reason=f"rollback target: {normalized}",
            updated_at=now,
        )
        self._items[target_key] = restored
        self.record_audit(
            _event(
                "rollback",
                ego_id,
                to_version,
                actor,
                normalized,
                approval_ref=approval_ref,
            )
        )
        return restored

    def record_audit(self, event: EgoAuditEvent) -> None:
        if any(item.event_id == event.event_id for item in self._audit):
            raise ValueError(f"duplicate E.G.O audit event: {event.event_id}")
        self._audit.append(event)

    def audit_events(
        self,
        ego_id: str | None = None,
    ) -> tuple[EgoAuditEvent, ...]:
        items = (
            item for item in self._audit
            if ego_id is None or item.ego_id == ego_id
        )
        return tuple(sorted(items, key=lambda item: (item.created_at, item.event_id)))

    def put_invalidation_candidate(
        self,
        candidate: EgoInvalidationCandidate,
    ) -> None:
        if candidate.candidate_id in self._invalidation:
            raise ValueError(
                f"duplicate E.G.O invalidation candidate: {candidate.candidate_id}"
            )
        self._invalidation[candidate.candidate_id] = candidate

    def get_invalidation_candidate(
        self,
        candidate_id: str,
    ) -> EgoInvalidationCandidate | None:
        return self._invalidation.get(candidate_id)

    def list_invalidation_candidates(
        self,
        *,
        status: str | None = None,
    ) -> tuple[EgoInvalidationCandidate, ...]:
        items = (
            item for item in self._invalidation.values()
            if status is None or item.status == status
        )
        return tuple(sorted(items, key=lambda item: (item.created_at, item.candidate_id)))

    def update_invalidation_candidate(
        self,
        candidate: EgoInvalidationCandidate,
    ) -> None:
        if candidate.candidate_id not in self._invalidation:
            raise KeyError(candidate.candidate_id)
        self._invalidation[candidate.candidate_id] = candidate


def _event(
    action: str,
    ego_id: str,
    version: str,
    actor: str,
    reason: str,
    *,
    approval_ref: str | None = None,
    related_version: str | None = None,
    candidate_id: str | None = None,
    metadata: dict | None = None,
) -> EgoAuditEvent:
    return EgoAuditEvent(
        event_id=f"ego-event-{uuid.uuid4().hex[:12]}",
        action=action,
        ego_id=ego_id,
        version=version,
        actor=actor,
        reason=reason,
        approval_ref=approval_ref,
        related_version=related_version,
        candidate_id=candidate_id,
        metadata=dict(metadata or {}),
    )
