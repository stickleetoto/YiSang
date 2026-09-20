from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .models import MemoryProposal, MemoryRecord


PROVIDER_WRITE_STATUSES = frozenset(
    {"committed", "pending", "quarantined", "rejected"}
)


@dataclass(frozen=True)
class ProviderWriteResult:
    provider_id: str
    status: str
    record: MemoryRecord | None = None
    proposal_ref: str | None = None
    reason: str = ""
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ValueError("provider_id must be non-empty")
        if self.status not in PROVIDER_WRITE_STATUSES:
            raise ValueError(f"unsupported provider write status: {self.status}")


@dataclass(frozen=True)
class ProviderCurrentState:
    provider_id: str
    topic_key: str
    current_memory_id: str | None
    confidence: float = 0.0
    superseded_ids: tuple[str, ...] = ()
    conflict_ids: tuple[str, ...] = ()
    reasoning: str = ""
    candidates: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderContext:
    provider_id: str
    text: str
    memories: tuple[MemoryRecord, ...] = ()
    context_ref: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class MemoryProvider(ABC):
    """Provider-neutral long-term memory surface for YiSang.

    This is intentionally higher-level than MemoryPort. MemoryPort remains the
    native authoritative storage contract; external providers may have their own
    lifecycle and write-governance semantics.
    """

    provider_id: str

    @abstractmethod
    def recall(self, query: str, *, limit: int = 8) -> list[MemoryRecord]:
        raise NotImplementedError

    @abstractmethod
    def remember(self, proposal: MemoryProposal) -> ProviderWriteResult:
        raise NotImplementedError

    @abstractmethod
    def get_current_state(self, topic_key: str) -> ProviderCurrentState:
        raise NotImplementedError

    @abstractmethod
    def get_context(
        self,
        query: str,
        *,
        limit: int = 8,
        char_budget: int = 2400,
    ) -> ProviderContext:
        raise NotImplementedError

    def observe_outcome(
        self,
        memory_ids: list[str],
        *,
        success: bool,
    ) -> None:
        """Optional provider feedback hook after request verification."""
        return None
