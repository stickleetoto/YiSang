from dataclasses import replace

from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.memory.projected import ProjectedMemoryPort
from yisang.memory.projection import LexicalMemoryProjection


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


def test_projection_is_rebuildable_from_authoritative_memory():
    authoritative = InMemoryMemoryPort()
    first = authoritative.commit(_proposal("python pytest debugger"))
    authoritative.commit(_proposal("rust cargo compiler"))

    projection = LexicalMemoryProjection()
    memory = ProjectedMemoryPort(
        authoritative,
        [projection],
        rebuild_on_start=False,
    )

    assert projection.size() == 0

    memory.rebuild_projections()

    assert projection.size() == 2
    found = memory.search("python pytest")
    assert [record.memory_id for record in found] == [first.memory_id]


def test_commit_updates_projection_without_rebuild():
    authoritative = InMemoryMemoryPort()
    projection = LexicalMemoryProjection()
    memory = ProjectedMemoryPort(authoritative, [projection])

    record = memory.commit(_proposal("persistent memory projection"))

    assert projection.size() == 1
    assert memory.search("projection")[0].memory_id == record.memory_id


def test_import_overwrite_refreshes_projection_content():
    authoritative = InMemoryMemoryPort()
    projection = LexicalMemoryProjection()
    memory = ProjectedMemoryPort(authoritative, [projection])

    original = memory.commit(_proposal("old searchable term"))
    updated = replace(
        original,
        content="new searchable term",
        updated_at=original.updated_at + 1,
    )

    memory.import_record(updated, overwrite=True)

    assert memory.search("old") == []
    assert memory.search("new")[0].memory_id == original.memory_id


def test_invalidated_record_is_removed_from_projection():
    authoritative = InMemoryMemoryPort()
    projection = LexicalMemoryProjection()
    memory = ProjectedMemoryPort(authoritative, [projection])

    record = memory.commit(_proposal("temporary visible fact"))
    invalidated = replace(
        record,
        invalidated=True,
        validation_state="invalidated",
    )

    memory.import_record(invalidated, overwrite=True)

    assert projection.size() == 0
    assert memory.search("visible") == []


def test_projection_loss_does_not_destroy_authoritative_memory():
    authoritative = InMemoryMemoryPort()
    memory = ProjectedMemoryPort(
        authoritative,
        [LexicalMemoryProjection()],
    )
    record = memory.commit(_proposal("survives projection loss"))

    replacement_projection = LexicalMemoryProjection()
    memory.projections = [replacement_projection]

    assert replacement_projection.size() == 0
    assert [item.memory_id for item in memory.all()] == [record.memory_id]

    memory.rebuild_projections()

    assert replacement_projection.size() == 1
    assert memory.search("projection loss")[0].memory_id == record.memory_id


def test_lexical_projection_prefers_more_query_overlap():
    authoritative = InMemoryMemoryPort()
    projection = LexicalMemoryProjection()
    memory = ProjectedMemoryPort(authoritative, [projection])

    broad = memory.commit(_proposal("python repository"))
    specific = memory.commit(_proposal("python pytest repository"))

    found = memory.search("python pytest", limit=2)

    assert found[0].memory_id == specific.memory_id
    assert found[1].memory_id == broad.memory_id
