from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import time
from typing import Any

from .models import EgoManifest
from .package import semantic_version_key


EGO_INSTALL_STATES = frozenset({"active", "disabled", "superseded"})
EGO_AUDIT_ACTIONS = frozenset(
    {
        "install",
        "supersede",
        "disable",
        "rollback",
        "invalidation_candidate_created",
        "invalidation_candidate_approved",
        "invalidation_candidate_rejected",
    }
)
EGO_INVALIDATION_STATES = frozenset({"pending", "approved", "rejected"})


@dataclass(frozen=True)
class InstalledEgoPackage:
    ego_id: str
    version: str
    manifest: EgoManifest
    state: str = "active"
    source_artifact_id: str | None = None
    approval_ref: str | None = None
    superseded_by_version: str | None = None
    status_reason: str = ""
    installed_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.ego_id.strip():
            raise ValueError("ego_id must be non-empty")
        if self.manifest.ego_id != self.ego_id:
            raise ValueError("installed ego_id must match manifest")
        if self.manifest.version != self.version:
            raise ValueError("installed version must match manifest")
        semantic_version_key(self.version)
        if self.state not in EGO_INSTALL_STATES:
            raise ValueError(f"unsupported E.G.O install state: {self.state}")

    @property
    def active(self) -> bool:
        return self.state == "active"


@dataclass(frozen=True)
class EgoAuditEvent:
    event_id: str
    action: str
    ego_id: str
    version: str
    actor: str
    reason: str
    approval_ref: str | None = None
    related_version: str | None = None
    candidate_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id must be non-empty")
        if self.action not in EGO_AUDIT_ACTIONS:
            raise ValueError(f"unsupported E.G.O audit action: {self.action}")
        if not self.ego_id.strip():
            raise ValueError("ego_id must be non-empty")
        semantic_version_key(self.version)
        if not self.actor.strip():
            raise ValueError("actor must be non-empty")
        if not self.reason.strip():
            raise ValueError("reason must be non-empty")
        if self.related_version is not None:
            semantic_version_key(self.related_version)


@dataclass(frozen=True)
class EgoInvalidationCandidate:
    candidate_id: str
    ego_id: str
    version: str
    replay_run_id: str
    failed_tests: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    reason: str
    source_artifact_id: str | None = None
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    resolved_at: float | None = None
    resolution_actor: str | None = None
    approval_ref: str | None = None
    resolution_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise ValueError("candidate_id must be non-empty")
        if not self.ego_id.strip():
            raise ValueError("ego_id must be non-empty")
        semantic_version_key(self.version)
        if not self.replay_run_id.strip():
            raise ValueError("replay_run_id must be non-empty")
        if not self.failed_tests:
            raise ValueError("invalidation candidate requires failed tests")
        if not self.reason.strip():
            raise ValueError("reason must be non-empty")
        if self.status not in EGO_INVALIDATION_STATES:
            raise ValueError(
                f"unsupported invalidation candidate status: {self.status}"
            )
        if self.status == "pending" and self.resolved_at is not None:
            raise ValueError("pending invalidation candidate cannot be resolved")


class EgoPort(ABC):
    """Authoritative durable E.G.O installation and lifecycle state."""

    @abstractmethod
    def install(
        self,
        package: InstalledEgoPackage,
        *,
        supersede_active: bool = True,
        actor: str = "system",
        approval_ref: str | None = None,
    ) -> InstalledEgoPackage:
        raise NotImplementedError

    @abstractmethod
    def get(
        self,
        ego_id: str,
        version: str | None = None,
    ) -> InstalledEgoPackage | None:
        raise NotImplementedError

    @abstractmethod
    def list_versions(self, ego_id: str) -> tuple[InstalledEgoPackage, ...]:
        raise NotImplementedError

    @abstractmethod
    def list_active(self) -> tuple[InstalledEgoPackage, ...]:
        raise NotImplementedError

    @abstractmethod
    def disable(
        self,
        ego_id: str,
        version: str,
        *,
        reason: str,
        actor: str = "system",
        approval_ref: str | None = None,
    ) -> InstalledEgoPackage:
        raise NotImplementedError

    @abstractmethod
    def rollback(
        self,
        ego_id: str,
        to_version: str,
        *,
        reason: str,
        actor: str = "system",
        approval_ref: str | None = None,
    ) -> InstalledEgoPackage:
        raise NotImplementedError

    @abstractmethod
    def record_audit(self, event: EgoAuditEvent) -> None:
        raise NotImplementedError

    @abstractmethod
    def audit_events(
        self,
        ego_id: str | None = None,
    ) -> tuple[EgoAuditEvent, ...]:
        raise NotImplementedError

    @abstractmethod
    def put_invalidation_candidate(
        self,
        candidate: EgoInvalidationCandidate,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_invalidation_candidate(
        self,
        candidate_id: str,
    ) -> EgoInvalidationCandidate | None:
        raise NotImplementedError

    @abstractmethod
    def list_invalidation_candidates(
        self,
        *,
        status: str | None = None,
    ) -> tuple[EgoInvalidationCandidate, ...]:
        raise NotImplementedError

    @abstractmethod
    def update_invalidation_candidate(
        self,
        candidate: EgoInvalidationCandidate,
    ) -> None:
        raise NotImplementedError
