from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from threading import RLock
from typing import Any
import time
import uuid

from .models import MemoryProposal


@dataclass(frozen=True)
class QuarantinedMemory:
    quarantine_id: str
    proposal: MemoryProposal
    reason: str
    risk_flags: tuple[str, ...] = ()
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class QuarantinePort(ABC):
    @abstractmethod
    def put(
        self,
        proposal: MemoryProposal,
        *,
        reason: str,
        risk_flags: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> QuarantinedMemory:
        raise NotImplementedError

    @abstractmethod
    def get(self, quarantine_id: str) -> QuarantinedMemory | None:
        raise NotImplementedError

    @abstractmethod
    def all(self) -> list[QuarantinedMemory]:
        raise NotImplementedError

    @abstractmethod
    def remove(self, quarantine_id: str) -> QuarantinedMemory | None:
        raise NotImplementedError


class InMemoryQuarantinePort(QuarantinePort):
    def __init__(self) -> None:
        self._lock = RLock()
        self._items: dict[str, QuarantinedMemory] = {}

    def put(
        self,
        proposal: MemoryProposal,
        *,
        reason: str,
        risk_flags: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> QuarantinedMemory:
        item = QuarantinedMemory(
            quarantine_id=f"qmem-{uuid.uuid4().hex[:12]}",
            proposal=proposal,
            reason=reason,
            risk_flags=tuple(risk_flags),
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._items[item.quarantine_id] = item
        return item

    def get(self, quarantine_id: str) -> QuarantinedMemory | None:
        with self._lock:
            return self._items.get(quarantine_id)

    def all(self) -> list[QuarantinedMemory]:
        with self._lock:
            return sorted(
                self._items.values(),
                key=lambda item: (item.created_at, item.quarantine_id),
            )

    def remove(self, quarantine_id: str) -> QuarantinedMemory | None:
        with self._lock:
            return self._items.pop(quarantine_id, None)
