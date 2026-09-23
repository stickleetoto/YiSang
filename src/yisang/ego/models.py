from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


EGO_PACKAGE_SCHEMA_VERSION = 2
EGO_RUNTIME_TYPES = frozenset({"prompt", "native", "wasm", "remote"})
EGO_DETAIL_LEVELS = frozenset({"metadata", "full"})
JSON_SCHEMA_2020_12 = "https://json-schema.org/draft/2020-12/schema"


@dataclass(frozen=True)
class EgoRiskHints:
    """Untrusted routing/UI hints, not authorization decisions.

    Defaults mirror the cautious MCP tool-annotation posture.
    """

    read_only: bool = False
    destructive: bool = True
    idempotent: bool = False
    open_world: bool = True


@dataclass(frozen=True)
class EgoManifest:
    # v1-compatible core fields. Keep ordering stable for existing callers.
    ego_id: str
    name: str
    provides: tuple[str, ...]
    keywords: tuple[str, ...] = ()
    instructions: str = ""
    permissions: dict[str, str | bool] = field(default_factory=dict)

    # v2 capability-package metadata.
    schema_version: int = 1
    version: str = "1.0.0"
    description: str = ""
    tags: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    risk: EgoRiskHints = field(default_factory=EgoRiskHints)
    runtime_type: str = "prompt"
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    resources: tuple[str, ...] = ()
    evals: tuple[str, ...] = ()
    package_digest: str | None = None
    detail_level: str = "full"

    def __post_init__(self) -> None:
        if not self.ego_id.strip():
            raise ValueError("ego_id must be non-empty")
        if not self.name.strip():
            raise ValueError("name must be non-empty")
        if not self.version.strip():
            raise ValueError("version must be non-empty")
        if self.schema_version <= 0:
            raise ValueError("schema_version must be positive")
        if self.runtime_type not in EGO_RUNTIME_TYPES:
            raise ValueError(
                f"unsupported E.G.O runtime_type: {self.runtime_type}"
            )
        if self.detail_level not in EGO_DETAIL_LEVELS:
            raise ValueError(
                f"unsupported E.G.O detail_level: {self.detail_level}"
            )
        if self.package_digest is not None:
            if not self.package_digest.startswith("sha256:"):
                raise ValueError("package_digest must use sha256:")
            digest = self.package_digest.removeprefix("sha256:")
            if len(digest) != 64:
                raise ValueError("package_digest sha256 must be 64 hex chars")

    @property
    def is_v2(self) -> bool:
        return self.schema_version >= EGO_PACKAGE_SCHEMA_VERSION

    @property
    def is_fully_loaded(self) -> bool:
        return self.detail_level == "full"
