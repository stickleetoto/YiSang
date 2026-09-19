from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from typing import Any
import json
import time
import uuid

from .models import MemoryRecord


@dataclass(frozen=True)
class MemoryMutation:
    mutation_id: str
    memory_id: str
    operation: str
    actor: str
    reason: str
    created_at: float = field(default_factory=time.time)
    evidence_refs: tuple[str, ...] = ()
    before_sha256: str | None = None
    after_sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.mutation_id.strip():
            raise ValueError("mutation_id must be non-empty")
        if not self.memory_id.strip():
            raise ValueError("memory_id must be non-empty")
        if not self.operation.strip():
            raise ValueError("operation must be non-empty")
        if not self.actor.strip():
            raise ValueError("actor must be non-empty")
        if not self.reason.strip():
            raise ValueError("reason must be non-empty")


def new_memory_mutation(
    *,
    memory_id: str,
    operation: str,
    actor: str,
    reason: str,
    evidence_refs: tuple[str, ...] = (),
    before: MemoryRecord | None = None,
    after: MemoryRecord | None = None,
    metadata: dict[str, Any] | None = None,
) -> MemoryMutation:
    return MemoryMutation(
        mutation_id=f"mmut-{uuid.uuid4().hex[:12]}",
        memory_id=memory_id,
        operation=operation,
        actor=actor,
        reason=reason,
        evidence_refs=tuple(evidence_refs),
        before_sha256=record_fingerprint(before) if before is not None else None,
        after_sha256=record_fingerprint(after) if after is not None else None,
        metadata=dict(metadata or {}),
    )


def record_fingerprint(record: MemoryRecord) -> str:
    raw = asdict(record)
    raw["evidence_refs"] = list(record.evidence_refs)
    encoded = json.dumps(
        raw,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()
