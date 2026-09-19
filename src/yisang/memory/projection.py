from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import re
from threading import RLock

from .models import MemoryRecord

_TOKEN_RE = re.compile(r"[A-Za-z0-9_가-힣]+")


@dataclass(frozen=True)
class MemoryHit:
    memory_id: str
    score: float
    projection: str


class MemoryProjection(ABC):
    """Rebuildable read-side projection over authoritative memory."""

    projection_id: str

    @abstractmethod
    def rebuild(self, records: list[MemoryRecord]) -> None:
        raise NotImplementedError

    @abstractmethod
    def upsert(self, record: MemoryRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def remove(self, memory_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str, *, limit: int = 8) -> list[MemoryHit]:
        raise NotImplementedError

    @abstractmethod
    def size(self) -> int:
        raise NotImplementedError


class LexicalMemoryProjection(MemoryProjection):
    """Small deterministic lexical projection.

    This is intentionally not authoritative storage. It can be deleted and
    rebuilt entirely from MemoryPort records.
    """

    projection_id = "lexical-v1"

    def __init__(self) -> None:
        self._lock = RLock()
        self._records: dict[str, MemoryRecord] = {}
        self._terms: dict[str, frozenset[str]] = {}

    def rebuild(self, records: list[MemoryRecord]) -> None:
        replacement_records: dict[str, MemoryRecord] = {}
        replacement_terms: dict[str, frozenset[str]] = {}
        for record in records:
            if record.invalidated or not record.is_durable:
                continue
            replacement_records[record.memory_id] = record
            replacement_terms[record.memory_id] = _terms(record.content)

        with self._lock:
            self._records = replacement_records
            self._terms = replacement_terms

    def upsert(self, record: MemoryRecord) -> None:
        with self._lock:
            if record.invalidated or not record.is_durable:
                self._records.pop(record.memory_id, None)
                self._terms.pop(record.memory_id, None)
                return
            self._records[record.memory_id] = record
            self._terms[record.memory_id] = _terms(record.content)

    def remove(self, memory_id: str) -> None:
        with self._lock:
            self._records.pop(memory_id, None)
            self._terms.pop(memory_id, None)

    def search(self, query: str, *, limit: int = 8) -> list[MemoryHit]:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        if limit == 0:
            return []

        query_terms = _terms(query)
        if not query_terms:
            return []

        ranked: list[tuple[float, str]] = []
        with self._lock:
            for memory_id, record_terms in self._terms.items():
                overlap = len(query_terms & record_terms)
                if overlap == 0:
                    continue
                record = self._records[memory_id]
                coverage = overlap / max(1, len(query_terms))
                score = (
                    float(overlap)
                    + coverage
                    + record.confidence * 0.10
                    + record.importance * 0.05
                )
                ranked.append((score, memory_id))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [
            MemoryHit(
                memory_id=memory_id,
                score=score,
                projection=self.projection_id,
            )
            for score, memory_id in ranked[:limit]
        ]

    def size(self) -> int:
        with self._lock:
            return len(self._records)


def _terms(text: str) -> frozenset[str]:
    return frozenset(
        match.group(0).lower()
        for match in _TOKEN_RE.finditer(text)
    )
