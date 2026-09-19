from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.memory.pipeline import MemoryWritePipeline
from yisang.memory.projected import ProjectedMemoryPort
from yisang.memory.projection import LexicalMemoryProjection
from yisang.memory.quarantine import InMemoryQuarantinePort
from yisang.memory.sqlite import SQLiteMemoryPort


def _proposal(content="revocable fact"):
    return MemoryProposal(
        content=content,
        kind="semantic",
        source_engine="engine-a",
        confidence=0.95,
        evidence=["tool:verified"],
        trust_class="verified",
        importance=0.8,
        writer="governor",
    )


def test_in_memory_revoke_preserves_record_and_audit_history():
    memory = InMemoryMemoryPort()
    record = memory.commit(_proposal())

    revoked = memory.invalidate(
        record.memory_id,
        actor="reviewer",
        reason="source retracted",
        evidence_refs=("review:1",),
    )

    assert revoked.invalidated is True
    assert revoked.validation_state == "invalidated"
    assert memory.search("revocable") == []

    history = memory.mutations(record.memory_id)
    assert [item.operation for item in history] == ["commit", "invalidate"]
    assert history[-1].actor == "reviewer"
    assert history[-1].reason == "source retracted"
    assert history[-1].before_sha256
    assert history[-1].after_sha256
    assert history[-1].before_sha256 != history[-1].after_sha256


def test_revalidate_restores_searchability():
    memory = InMemoryMemoryPort()
    record = memory.commit(_proposal())
    memory.invalidate(
        record.memory_id,
        actor="reviewer",
        reason="temporary hold",
    )

    restored = memory.revalidate(
        record.memory_id,
        actor="reviewer",
        reason="evidence reconfirmed",
        evidence_refs=("review:2",),
    )

    assert restored.invalidated is False
    assert restored.validation_state == "committed"
    assert memory.search("revocable")[0].memory_id == record.memory_id
    assert [item.operation for item in memory.mutations(record.memory_id)] == [
        "commit",
        "invalidate",
        "revalidate",
    ]


def test_sqlite_mutation_history_survives_reopen(tmp_path):
    path = tmp_path / "memory.db"
    first = SQLiteMemoryPort(path)
    record = first.commit(_proposal("sqlite lifecycle memory"))
    first.invalidate(
        record.memory_id,
        actor="reviewer",
        reason="revoked",
        evidence_refs=("ticket:1",),
    )
    first.close()

    second = SQLiteMemoryPort(path)
    loaded = second.get(record.memory_id)
    history = second.mutations(record.memory_id)

    assert loaded is not None
    assert loaded.invalidated is True
    assert [item.operation for item in history] == ["commit", "invalidate"]
    assert history[-1].evidence_refs == ("ticket:1",)
    second.close()


def test_projected_memory_removes_and_restores_revoked_record():
    authoritative = InMemoryMemoryPort()
    projection = LexicalMemoryProjection()
    memory = ProjectedMemoryPort(authoritative, [projection])
    record = memory.commit(_proposal("projected lifecycle memory"))

    assert projection.size() == 1

    memory.invalidate(
        record.memory_id,
        actor="reviewer",
        reason="revoke",
    )
    assert projection.size() == 0
    assert memory.search("projected") == []

    memory.revalidate(
        record.memory_id,
        actor="reviewer",
        reason="restore",
    )
    assert projection.size() == 1
    assert memory.search("projected")[0].memory_id == record.memory_id


def test_pipeline_revoke_and_revalidate_delegate_to_authoritative_memory():
    memory = InMemoryMemoryPort()
    pipeline = MemoryWritePipeline(
        memory=memory,
        governor=MemoryGovernor(),
        quarantine=InMemoryQuarantinePort(),
    )
    committed = pipeline.submit(_proposal("pipeline lifecycle memory")).record

    revoked = pipeline.revoke(
        committed.memory_id,
        actor="admin",
        reason="manual revocation",
    )
    restored = pipeline.revalidate(
        committed.memory_id,
        actor="admin",
        reason="manual restore",
    )

    assert revoked.invalidated is True
    assert restored.invalidated is False
    assert len(memory.mutations(committed.memory_id)) == 3
