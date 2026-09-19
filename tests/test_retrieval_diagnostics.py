from dataclasses import replace
import time

from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.memory.projected import ProjectedMemoryPort
from yisang.memory.projection import LexicalMemoryProjection
from yisang.memory.retrieval import RetrievalPolicy


def _proposal(content, *, kind="semantic", importance=0.5, trust_class="verified"):
    return MemoryProposal(
        content=content,
        kind=kind,
        source_engine="test",
        confidence=0.9,
        evidence=[f"seed:{content}"],
        trust_class=trust_class,
        importance=importance,
    )


def test_search_with_diagnostics_reports_projection_and_selected_ids():
    authoritative = InMemoryMemoryPort()
    projection = LexicalMemoryProjection()
    memory = ProjectedMemoryPort(authoritative, [projection])

    first = memory.commit(_proposal("python pytest workflow", importance=0.9))
    memory.commit(_proposal("python repository", importance=0.2))

    result = memory.search_with_diagnostics("python pytest", limit=2)

    assert result.records[0].memory_id == first.memory_id
    assert result.diagnostics.selected_ids[0] == first.memory_id
    assert result.diagnostics.projection_traces[0].projection_id == projection.projection_id
    assert result.diagnostics.projection_traces[0].hit_count == 2
    assert result.diagnostics.total_latency_ms >= 0


def test_preferred_procedural_kind_can_rerank_equal_hits():
    authoritative = InMemoryMemoryPort()
    projection = LexicalMemoryProjection()
    memory = ProjectedMemoryPort(
        authoritative,
        [projection],
        retrieval_policy=RetrievalPolicy(
            importance_weight=0.0,
            recency_weight=0.0,
            trust_weight=0.0,
            preferred_kind_weight=1.0,
        ),
    )

    semantic = memory.commit(_proposal("deploy service", kind="semantic"))
    procedural = memory.commit(_proposal("deploy service", kind="procedural"))

    result = memory.search_with_diagnostics(
        "deploy service",
        limit=2,
        preferred_kinds=("procedural",),
    )

    assert result.records[0].memory_id == procedural.memory_id
    assert result.records[1].memory_id == semantic.memory_id


def test_importance_breaks_equal_projection_rank_when_weighted():
    authoritative = InMemoryMemoryPort()
    projection = LexicalMemoryProjection()
    memory = ProjectedMemoryPort(
        authoritative,
        [projection],
        retrieval_policy=RetrievalPolicy(
            importance_weight=1.0,
            recency_weight=0.0,
            trust_weight=0.0,
            preferred_kind_weight=0.0,
        ),
    )

    low = memory.commit(_proposal("same query", importance=0.1))
    high = memory.commit(_proposal("same query", importance=0.9))

    result = memory.search_with_diagnostics("same query", limit=2)

    assert result.records[0].memory_id == high.memory_id
    assert result.records[1].memory_id == low.memory_id


def test_recency_component_prefers_recent_record_when_other_scores_equal():
    authoritative = InMemoryMemoryPort()
    projection = LexicalMemoryProjection()
    policy = RetrievalPolicy(
        importance_weight=0.0,
        recency_weight=1.0,
        trust_weight=0.0,
        preferred_kind_weight=0.0,
        recency_half_life_seconds=60.0,
    )
    memory = ProjectedMemoryPort(
        authoritative,
        [projection],
        retrieval_policy=policy,
    )

    old = memory.commit(_proposal("status server"))
    recent = memory.commit(_proposal("status server"))

    authoritative.import_record(
        replace(
            old,
            updated_at=time.time() - 600,
            created_at=time.time() - 600,
            valid_from=time.time() - 600,
        ),
        overwrite=True,
    )
    memory.rebuild_projections()

    result = memory.search_with_diagnostics("status server", limit=2)

    assert result.records[0].memory_id == recent.memory_id


def test_zero_limit_returns_empty_diagnostics():
    memory = ProjectedMemoryPort(
        InMemoryMemoryPort(),
        [LexicalMemoryProjection()],
    )

    result = memory.search_with_diagnostics("anything", limit=0)

    assert result.records == ()
    assert result.diagnostics.selected_ids == ()
    assert result.diagnostics.candidates == ()
