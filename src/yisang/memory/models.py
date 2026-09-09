from dataclasses import dataclass, field
from typing import Any
import time
import uuid

@dataclass
class MemoryRecord:
    memory_id: str
    kind: str
    content: str
    source: str
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class MemoryProposal:
    content: str
    kind: str = "semantic"
    source_engine: str = "unknown"
    confidence: float = 0.5
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> MemoryRecord:
        return MemoryRecord(
            memory_id=f"mem-{uuid.uuid4().hex[:12]}",
            kind=self.kind,
            content=self.content,
            source=self.source_engine,
            confidence=self.confidence,
            metadata={
                **self.metadata,
                "evidence": list(self.evidence),
                "committed_at": time.time(),
            },
        )

@dataclass(frozen=True)
class GovernanceDecision:
    accepted: bool
    reason: str
