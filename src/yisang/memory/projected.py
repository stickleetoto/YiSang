from __future__ import annotations

from collections import defaultdict

from .lifecycle import MemoryMutation
from .models import MemoryProposal, MemoryRecord
from .port import MemoryPort
from .projection import MemoryProjection


class ProjectedMemoryPort(MemoryPort):
    """MemoryPort wrapper with rebuildable read-side projections.

    The wrapped MemoryPort remains authoritative. Search indexes can disappear
    and be reconstructed from authoritative records without data loss.
    """

    def __init__(
        self,
        authoritative: MemoryPort,
        projections: list[MemoryProjection],
        *,
        rebuild_on_start: bool = True,
        projection_weights: dict[str, float] | None = None,
        rrf_k: int = 60,
    ) -> None:
        if not projections:
            raise ValueError("at least one projection is required")
        if rrf_k < 0:
            raise ValueError("rrf_k must be non-negative")
        self.authoritative = authoritative
        self.projections = list(projections)
        self.rrf_k = rrf_k
        self.projection_weights = dict(projection_weights or {})
        for projection_id, weight in self.projection_weights.items():
            if weight <= 0:
                raise ValueError(
                    f"projection weight must be positive: {projection_id}"
                )
        if rebuild_on_start:
            self.rebuild_projections()

    def rebuild_projections(self) -> None:
        records = self.authoritative.all()
        for projection in self.projections:
            projection.rebuild(records)

    def projection_sizes(self) -> dict[str, int]:
        return {
            projection.projection_id: projection.size()
            for projection in self.projections
        }

    def search(self, query: str, *, limit: int = 8) -> list[MemoryRecord]:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        if limit == 0:
            return []

        # Hydration always comes from the authoritative store.
        records_by_id = {
            record.memory_id: record
            for record in self.authoritative.all()
            if not record.invalidated
        }

        scores: dict[str, float] = defaultdict(float)
        for projection in self.projections:
            hits = projection.search(query, limit=max(limit * 4, limit))
            weight = self.projection_weights.get(projection.projection_id, 1.0)
            for rank, hit in enumerate(hits, start=1):
                # Reciprocal-rank fusion deliberately ignores raw projection
                # score scales so BM25, lexical, vector, and future indexes can
                # be combined without pretending their scores are comparable.
                scores[hit.memory_id] += weight / (self.rrf_k + rank)

        ranked_ids = sorted(
            (
                (score, memory_id)
                for memory_id, score in scores.items()
                if memory_id in records_by_id
            ),
            key=lambda item: (-item[0], item[1]),
        )
        return [
            records_by_id[memory_id]
            for _, memory_id in ranked_ids[:limit]
        ]

    def commit(self, proposal: MemoryProposal) -> MemoryRecord:
        record = self.authoritative.commit(proposal)
        for projection in self.projections:
            projection.upsert(record)
        return record

    def import_record(
        self,
        record: MemoryRecord,
        *,
        overwrite: bool = False,
    ) -> MemoryRecord:
        restored = self.authoritative.import_record(
            record,
            overwrite=overwrite,
        )
        for projection in self.projections:
            projection.upsert(restored)
        return restored

    def all(self) -> list[MemoryRecord]:
        return self.authoritative.all()

    def mutations(self, memory_id: str | None = None) -> list[MemoryMutation]:
        return self.authoritative.mutations(memory_id)

    def invalidate(
        self,
        memory_id: str,
        *,
        actor: str,
        reason: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> MemoryRecord:
        record = self.authoritative.invalidate(
            memory_id,
            actor=actor,
            reason=reason,
            evidence_refs=evidence_refs,
        )
        for projection in self.projections:
            projection.upsert(record)
        return record

    def revalidate(
        self,
        memory_id: str,
        *,
        actor: str,
        reason: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> MemoryRecord:
        record = self.authoritative.revalidate(
            memory_id,
            actor=actor,
            reason=reason,
            evidence_refs=evidence_refs,
        )
        for projection in self.projections:
            projection.upsert(record)
        return record
