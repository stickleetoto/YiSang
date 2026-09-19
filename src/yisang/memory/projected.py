from __future__ import annotations

from collections import defaultdict
from time import perf_counter

from .lifecycle import MemoryMutation
from .models import MemoryProposal, MemoryRecord
from .port import MemoryPort
from .projection import MemoryProjection
from .retrieval import (
    ProjectionTrace,
    RetrievalCandidateTrace,
    RetrievalDiagnostics,
    RetrievalPolicy,
    RetrievalResult,
    metadata_rerank_score,
)


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
        retrieval_policy: RetrievalPolicy | None = None,
    ) -> None:
        if not projections:
            raise ValueError("at least one projection is required")
        if rrf_k < 0:
            raise ValueError("rrf_k must be non-negative")
        self.authoritative = authoritative
        self.projections = list(projections)
        self.rrf_k = rrf_k
        self.projection_weights = dict(projection_weights or {})
        self.retrieval_policy = retrieval_policy or RetrievalPolicy()
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
        return list(
            self.search_with_diagnostics(
                query,
                limit=limit,
            ).records
        )

    def search_with_diagnostics(
        self,
        query: str,
        *,
        limit: int = 8,
        preferred_kinds: tuple[str, ...] = (),
    ) -> RetrievalResult:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        if limit == 0:
            return RetrievalResult(
                records=(),
                diagnostics=RetrievalDiagnostics(
                    query=query,
                    limit=limit,
                    preferred_kinds=tuple(preferred_kinds),
                    projection_traces=(),
                    candidates=(),
                    selected_ids=(),
                    total_latency_ms=0.0,
                ),
            )

        started = perf_counter()

        records_by_id = {
            record.memory_id: record
            for record in self.authoritative.all()
            if record.is_active()
        }

        fusion_scores: dict[str, float] = defaultdict(float)
        projection_traces: list[ProjectionTrace] = []
        for projection in self.projections:
            projection_started = perf_counter()
            hits = projection.search(query, limit=max(limit * 4, limit))
            projection_latency_ms = (
                perf_counter() - projection_started
            ) * 1000
            projection_traces.append(
                ProjectionTrace(
                    projection_id=projection.projection_id,
                    hit_ids=tuple(hit.memory_id for hit in hits),
                    hit_count=len(hits),
                    latency_ms=projection_latency_ms,
                )
            )
            weight = self.projection_weights.get(projection.projection_id, 1.0)
            for rank, hit in enumerate(hits, start=1):
                fusion_scores[hit.memory_id] += weight / (self.rrf_k + rank)

        candidates: list[RetrievalCandidateTrace] = []
        for memory_id, fusion_score in fusion_scores.items():
            record = records_by_id.get(memory_id)
            if record is None:
                continue
            metadata_score, age_seconds = metadata_rerank_score(
                record,
                policy=self.retrieval_policy,
                preferred_kinds=tuple(preferred_kinds),
            )
            candidates.append(
                RetrievalCandidateTrace(
                    memory_id=memory_id,
                    fusion_score=fusion_score,
                    metadata_score=metadata_score,
                    final_score=fusion_score + metadata_score,
                    importance=record.importance,
                    trust_class=record.trust_class,
                    kind=record.kind,
                    age_seconds=age_seconds,
                )
            )

        candidates.sort(
            key=lambda item: (-item.final_score, item.memory_id)
        )
        selected_ids = tuple(
            item.memory_id for item in candidates[:limit]
        )
        selected = tuple(records_by_id[memory_id] for memory_id in selected_ids)
        self.authoritative.mark_retrieved(list(selected_ids))

        diagnostics = RetrievalDiagnostics(
            query=query,
            limit=limit,
            preferred_kinds=tuple(preferred_kinds),
            projection_traces=tuple(projection_traces),
            candidates=tuple(candidates),
            selected_ids=selected_ids,
            total_latency_ms=(perf_counter() - started) * 1000,
        )
        return RetrievalResult(
            records=selected,
            diagnostics=diagnostics,
        )

    def commit(self, proposal: MemoryProposal) -> MemoryRecord:
        record = self.authoritative.commit(proposal)
        for projection in self.projections:
            projection.upsert(record)
        return record

    def mark_retrieved(self, memory_ids: list[str]) -> None:
        self.authoritative.mark_retrieved(memory_ids)

    def record_outcome(self, memory_ids: list[str], *, success: bool) -> None:
        self.authoritative.record_outcome(memory_ids, success=success)

    def supersede(
        self,
        memory_id: str,
        *,
        superseded_by_id: str,
        actor: str,
        reason: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> MemoryRecord:
        record = self.authoritative.supersede(
            memory_id,
            superseded_by_id=superseded_by_id,
            actor=actor,
            reason=reason,
            evidence_refs=evidence_refs,
        )
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
