import pytest

from yisang.memory.fts import SQLiteFTSProjection
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.memory.projected import ProjectedMemoryPort
from yisang.memory.projection import LexicalMemoryProjection
from yisang.memory.retrieval import RetrievalPolicy


def _proposal(content, *, importance=0.5):
    return MemoryProposal(
        content=content,
        kind="semantic",
        source_engine="test",
        confidence=0.9,
        evidence=[f"seed:{content}"],
        trust_class="verified",
        importance=importance,
    )


def _fts(tmp_path):
    try:
        return SQLiteFTSProjection(tmp_path / "fts.db")
    except RuntimeError as exc:
        pytest.skip(str(exc))


def test_fts_projection_rebuilds_from_authoritative_records(tmp_path):
    authoritative = InMemoryMemoryPort()
    python = authoritative.commit(_proposal("python pytest repository"))
    authoritative.commit(_proposal("rust cargo compiler"))

    fts = _fts(tmp_path)
    fts.rebuild(authoritative.all())

    found = fts.search("python pytest")

    assert fts.size() == 2
    assert found
    assert found[0].memory_id == python.memory_id
    fts.close()


def test_fts_projection_tracks_upsert_and_invalidation(tmp_path):
    authoritative = InMemoryMemoryPort()
    fts = _fts(tmp_path)
    memory = ProjectedMemoryPort(authoritative, [fts])
    record = memory.commit(_proposal("durable searchable memory"))

    assert memory.search("searchable")[0].memory_id == record.memory_id

    memory.invalidate(
        record.memory_id,
        actor="reviewer",
        reason="source revoked",
    )

    assert fts.size() == 0
    assert memory.search("searchable") == []

    memory.revalidate(
        record.memory_id,
        actor="reviewer",
        reason="source restored",
    )

    assert fts.size() == 1
    assert memory.search("searchable")[0].memory_id == record.memory_id
    fts.close()


def test_hybrid_rrf_combines_lexical_and_fts_without_raw_score_coupling(tmp_path):
    authoritative = InMemoryMemoryPort()
    lexical = LexicalMemoryProjection()
    fts = _fts(tmp_path)
    memory = ProjectedMemoryPort(
        authoritative,
        [lexical, fts],
        rrf_k=60,
    )

    specific = memory.commit(_proposal("python pytest repository debugging"))
    memory.commit(_proposal("python repository"))
    memory.commit(_proposal("pytest testing only"))

    found = memory.search("python pytest", limit=3)

    assert found[0].memory_id == specific.memory_id
    assert {record.memory_id for record in found} == {
        record.memory_id for record in memory.all()
    }
    fts.close()


def test_projection_weights_can_bias_hybrid_fusion(tmp_path):
    authoritative = InMemoryMemoryPort()
    lexical = LexicalMemoryProjection()
    fts = _fts(tmp_path)
    memory = ProjectedMemoryPort(
        authoritative,
        [lexical, fts],
        projection_weights={
            lexical.projection_id: 0.5,
            fts.projection_id: 2.0,
        },
        retrieval_policy=RetrievalPolicy(
            importance_weight=0.0,
            recency_weight=0.0,
            trust_weight=0.0,
            preferred_kind_weight=0.0,
        ),
    )

    lexical_first = memory.commit(
        _proposal(
            "alpha beta gamma delta epsilon zeta eta theta",
            importance=1.0,
        )
    )
    fts_first = memory.commit(
        _proposal("alpha beta", importance=0.0)
    )

    lexical_hits = lexical.search("alpha beta")
    fts_hits = fts.search("alpha beta")
    assert lexical_hits[0].memory_id == lexical_first.memory_id
    assert fts_hits[0].memory_id == fts_first.memory_id

    found = memory.search("alpha beta")

    assert found[0].memory_id == fts_first.memory_id
    fts.close()


def test_hybrid_retrieval_rejects_non_positive_weights():
    authoritative = InMemoryMemoryPort()
    lexical = LexicalMemoryProjection()

    with pytest.raises(ValueError, match="weight"):
        ProjectedMemoryPort(
            authoritative,
            [lexical],
            projection_weights={lexical.projection_id: 0.0},
        )
