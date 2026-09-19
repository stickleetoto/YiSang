import pytest

from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.memory.projected import ProjectedMemoryPort
from yisang.memory.projection import LexicalMemoryProjection
from yisang.memory.vector import EmbeddingProvider, InMemoryVectorProjection


class FakeEmbeddingProvider(EmbeddingProvider):
    def embed(self, texts):
        vectors = []
        for text in texts:
            lowered = text.lower()
            vectors.append(
                (
                    1.0 if "python" in lowered else 0.0,
                    1.0 if "pytest" in lowered or "testing" in lowered else 0.0,
                    1.0 if "rust" in lowered else 0.0,
                )
            )
        return vectors


def _proposal(content):
    return MemoryProposal(
        content=content,
        kind="semantic",
        source_engine="test",
        confidence=0.9,
        evidence=[f"seed:{content}"],
        trust_class="verified",
    )


def test_vector_projection_rebuild_and_semantic_search():
    authoritative = InMemoryMemoryPort()
    python = authoritative.commit(_proposal("python testing workflow"))
    authoritative.commit(_proposal("rust cargo workflow"))

    vector = InMemoryVectorProjection(FakeEmbeddingProvider())
    vector.rebuild(authoritative.all())

    found = vector.search("python pytest")

    assert vector.size() == 2
    assert vector.dimension == 3
    assert found[0].memory_id == python.memory_id


def test_vector_projection_tracks_invalidation_and_revalidation():
    authoritative = InMemoryMemoryPort()
    vector = InMemoryVectorProjection(FakeEmbeddingProvider())
    memory = ProjectedMemoryPort(authoritative, [vector])
    record = memory.commit(_proposal("python testing memory"))

    assert vector.size() == 1

    memory.invalidate(
        record.memory_id,
        actor="reviewer",
        reason="revoked",
    )
    assert vector.size() == 0

    memory.revalidate(
        record.memory_id,
        actor="reviewer",
        reason="restored",
    )
    assert vector.size() == 1


def test_hybrid_lexical_vector_rrf_prefers_agreement():
    authoritative = InMemoryMemoryPort()
    lexical = LexicalMemoryProjection()
    vector = InMemoryVectorProjection(FakeEmbeddingProvider())
    memory = ProjectedMemoryPort(
        authoritative,
        [lexical, vector],
        projection_weights={
            lexical.projection_id: 1.0,
            vector.projection_id: 1.0,
        },
    )

    strongest = memory.commit(_proposal("python pytest guide"))
    memory.commit(_proposal("python guide"))
    memory.commit(_proposal("testing guide"))

    found = memory.search("python pytest", limit=3)

    assert found[0].memory_id == strongest.memory_id


def test_vector_projection_rejects_dimension_changes():
    class BadProvider(EmbeddingProvider):
        def __init__(self):
            self.calls = 0

        def embed(self, texts):
            self.calls += 1
            if self.calls == 1:
                return [(1.0, 0.0) for _ in texts]
            return [(1.0, 0.0, 0.0) for _ in texts]

    authoritative = InMemoryMemoryPort()
    vector = InMemoryVectorProjection(BadProvider())
    memory = ProjectedMemoryPort(authoritative, [vector])
    memory.commit(_proposal("first memory"))

    with pytest.raises(ValueError, match="dimension"):
        memory.commit(_proposal("second memory"))


def test_vector_projection_can_filter_low_similarity():
    authoritative = InMemoryMemoryPort()
    vector = InMemoryVectorProjection(
        FakeEmbeddingProvider(),
        min_similarity=0.5,
    )
    memory = ProjectedMemoryPort(authoritative, [vector])
    python = memory.commit(_proposal("python pytest"))
    memory.commit(_proposal("rust cargo"))

    found = memory.search("python pytest")

    assert [record.memory_id for record in found] == [python.memory_id]
