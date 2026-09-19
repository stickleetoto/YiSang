from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import time
import uuid

MEMORY_SCHEMA_VERSION = 3
MEMORY_KINDS = frozenset({"episodic", "semantic", "procedural", "working"})
DURABLE_MEMORY_KINDS = frozenset({"episodic", "semantic", "procedural"})
TRUST_CLASSES = frozenset({"unknown", "trusted", "verified", "untrusted", "quarantined"})
VALIDATION_STATES = frozenset(
    {"proposed", "committed", "quarantined", "invalidated", "superseded"}
)


@dataclass
class MemoryRecord:
    memory_id: str
    kind: str
    content: str
    source: str
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    source_id: str | None = None
    source_type: str = "engine"
    evidence_refs: tuple[str, ...] = ()
    trust_class: str = "unknown"
    importance: float = 0.5
    writer: str = "unknown"
    validation_state: str = "committed"
    created_at: float = 0.0
    updated_at: float = 0.0
    valid_from: float = 0.0
    valid_until: float | None = None
    supersedes_id: str | None = None
    superseded_by_id: str | None = None
    last_used_at: float | None = None
    success_count: int = 0
    failure_count: int = 0
    schema_version: int = MEMORY_SCHEMA_VERSION
    invalidated: bool = False

    def __post_init__(self) -> None:
        _validate_probability("confidence", self.confidence)
        _validate_probability("importance", self.importance)
        if self.schema_version <= 0:
            raise ValueError("schema_version must be positive")
        if not self.memory_id.strip():
            raise ValueError("memory_id must be non-empty")
        if not self.kind.strip():
            raise ValueError("kind must be non-empty")
        if not self.content.strip():
            raise ValueError("content must be non-empty")
        if self.success_count < 0 or self.failure_count < 0:
            raise ValueError("memory outcome counters must be non-negative")
        if self.valid_until is not None and self.valid_until < self.valid_from:
            raise ValueError("valid_until must be >= valid_from")

    def is_active(self, *, at: float | None = None) -> bool:
        when = time.time() if at is None else float(at)
        if self.invalidated:
            return False
        if self.valid_from and when < self.valid_from:
            return False
        if self.valid_until is not None and when >= self.valid_until:
            return False
        return True

    @property
    def is_durable(self) -> bool:
        return self.kind in DURABLE_MEMORY_KINDS and self.is_active()


@dataclass
class MemoryProposal:
    content: str
    kind: str = "semantic"
    source_engine: str = "unknown"
    confidence: float = 0.5
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    source_id: str | None = None
    source_type: str = "engine"
    trust_class: str = "unknown"
    importance: float = 0.5
    writer: str | None = None
    valid_from: float | None = None
    valid_until: float | None = None
    supersedes_id: str | None = None

    def __post_init__(self) -> None:
        _validate_probability("confidence", self.confidence)
        _validate_probability("importance", self.importance)
        if not self.content.strip():
            raise ValueError("content must be non-empty")
        if not self.kind.strip():
            raise ValueError("kind must be non-empty")
        if not self.source_type.strip():
            raise ValueError("source_type must be non-empty")
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_until < self.valid_from
        ):
            raise ValueError("valid_until must be >= valid_from")

    def to_record(self) -> MemoryRecord:
        now = time.time()
        valid_from = now if self.valid_from is None else float(self.valid_from)
        return MemoryRecord(
            memory_id=f"mem-{uuid.uuid4().hex[:12]}",
            kind=self.kind,
            content=self.content,
            source=self.source_engine,
            confidence=self.confidence,
            metadata={
                **self.metadata,
                "evidence": list(self.evidence),
                "committed_at": now,
            },
            source_id=self.source_id,
            source_type=self.source_type,
            evidence_refs=tuple(self.evidence),
            trust_class=self.trust_class,
            importance=self.importance,
            writer=self.writer or self.source_engine,
            validation_state="committed",
            created_at=now,
            updated_at=now,
            valid_from=valid_from,
            valid_until=self.valid_until,
            supersedes_id=self.supersedes_id,
            schema_version=MEMORY_SCHEMA_VERSION,
            invalidated=False,
        )


@dataclass(frozen=True)
class GovernanceDecision:
    accepted: bool
    reason: str
    quarantine: bool = False
    risk_flags: tuple[str, ...] = ()


def _validate_probability(name: str, value: float) -> None:
    if not 0.0 <= float(value) <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
