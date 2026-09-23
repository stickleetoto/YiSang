from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import time

from .models import EgoManifest
from .package import semantic_version_key


EGO_INSTALL_STATES = frozenset({"active", "disabled", "superseded"})


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


class EgoPort(ABC):
    """Authoritative durable E.G.O installation state."""

    @abstractmethod
    def install(
        self,
        package: InstalledEgoPackage,
        *,
        supersede_active: bool = True,
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
    ) -> InstalledEgoPackage:
        raise NotImplementedError

    @abstractmethod
    def rollback(
        self,
        ego_id: str,
        to_version: str,
        *,
        reason: str,
    ) -> InstalledEgoPackage:
        raise NotImplementedError
