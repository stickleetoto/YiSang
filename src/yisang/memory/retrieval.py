from __future__ import annotations

from dataclasses import dataclass, field
from math import exp, log
from time import time
from typing import Any

from .models import MemoryRecord


@dataclass(frozen=True)
class RetrievalPolicy:
    """Metadata-aware reranking policy applied after projection fusion."""

    importance_weight: float = 0.10
    recency_weight: float = 0.05
    trust_weight: float = 0.05
    preferred_kind_weight: float = 0.10
    recency_half_life_seconds: float = 7 * 24 * 60 * 60

    def __post_init__(self) -> None:
        for name in (
            "importance_weight",
            "recency_weight",
            "trust_weight",
            "preferred_kind_weight",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.recency_half_life_seconds <= 0:
            raise ValueError("recency_half_life_seconds must be positive")


@dataclass(frozen=True)
class ProjectionTrace:
    projection_id: str
    hit_ids: tuple[str, ...]
    hit_count: int
    latency_ms: float


@dataclass(frozen=True)
class RetrievalCandidateTrace:
    memory_id: str
    fusion_score: float
    metadata_score: float
    final_score: float
    importance: float
    trust_class: str
    kind: str
    age_seconds: float | None


@dataclass(frozen=True)
class RetrievalDiagnostics:
    query: str
    limit: int
    preferred_kinds: tuple[str, ...]
    projection_traces: tuple[ProjectionTrace, ...]
    candidates: tuple[RetrievalCandidateTrace, ...]
    selected_ids: tuple[str, ...]
    total_latency_ms: float


@dataclass(frozen=True)
class RetrievalResult:
    records: tuple[MemoryRecord, ...]
    diagnostics: RetrievalDiagnostics


def metadata_rerank_score(
    record: MemoryRecord,
    *,
    policy: RetrievalPolicy,
    preferred_kinds: tuple[str, ...] = (),
    now: float | None = None,
) -> tuple[float, float | None]:
    when = time() if now is None else now
    score = 0.0

    score += policy.importance_weight * max(0.0, min(1.0, record.importance))

    trust_score = {
        "verified": 1.0,
        "trusted": 0.8,
        "unknown": 0.2,
        "untrusted": 0.0,
        "quarantined": 0.0,
    }.get(record.trust_class, 0.0)
    score += policy.trust_weight * trust_score

    if preferred_kinds and record.kind in preferred_kinds:
        score += policy.preferred_kind_weight

    reference_time = record.updated_at or record.created_at or record.valid_from
    age_seconds: float | None = None
    if reference_time and reference_time > 0:
        age_seconds = max(0.0, when - reference_time)
        decay = exp(
            -log(2.0) * age_seconds / policy.recency_half_life_seconds
        )
        score += policy.recency_weight * decay

    return score, age_seconds
