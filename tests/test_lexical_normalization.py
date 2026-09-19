from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.lexical import lexical_terms
from yisang.memory.models import MemoryProposal
from yisang.memory.projected import ProjectedMemoryPort
from yisang.memory.projection import LexicalMemoryProjection
from yisang.memory.sqlite import SQLiteMemoryPort


def _proposal(content):
    return MemoryProposal(
        content=content,
        kind="semantic",
        source_engine="test",
        confidence=0.95,
        evidence=["lexical:test"],
        trust_class="verified",
        writer="test",
    )


def test_lexical_terms_normalize_benchmark_morphology_and_identifiers():
    terms = lexical_terms(
        "E.G.O capabilities MemoryGovernor indexes rebuilt tools quarantined"
    )

    assert {
        "ego",
        "capability",
        "memory",
        "governor",
        "index",
        "rebuild",
        "tool",
        "quarantine",
    }.issubset(terms)


def test_projected_memory_matches_normalized_forms():
    memory = ProjectedMemoryPort(
        InMemoryMemoryPort(),
        [LexicalMemoryProjection()],
    )
    index_record = memory.commit(
        _proposal(
            "Read-side indexes can be rebuilt from authoritative memory."
        )
    )
    capability_record = memory.commit(
        _proposal(
            "E.G.O capabilities remain externalized across engine replacement."
        )
    )

    assert memory.search("rebuild search index")[0].memory_id == index_record.memory_id
    assert memory.search("ego capability")[0].memory_id == capability_record.memory_id


def test_in_memory_and_sqlite_search_share_normalized_terms(tmp_path):
    content = "Only currently exposed tools may be called."

    in_memory = InMemoryMemoryPort()
    in_record = in_memory.commit(_proposal(content))
    assert in_memory.search("tool capability")[0].memory_id == in_record.memory_id

    sqlite = SQLiteMemoryPort(tmp_path / "memory.db")
    sql_record = sqlite.commit(_proposal(content))
    assert sqlite.search("tool capability")[0].memory_id == sql_record.memory_id
    sqlite.close()


def test_quarantine_form_matches_quarantined_text():
    memory = ProjectedMemoryPort(
        InMemoryMemoryPort(),
        [LexicalMemoryProjection()],
    )
    record = memory.commit(
        _proposal(
            "Untrusted proposals stay quarantined until review."
        )
    )

    assert memory.search("quarantine bypass")[0].memory_id == record.memory_id
