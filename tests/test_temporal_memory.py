import time

from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MEMORY_SCHEMA_VERSION, MemoryProposal
from yisang.memory.pipeline import MemoryWritePipeline, MemoryWriteStatus
from yisang.memory.projected import ProjectedMemoryPort
from yisang.memory.projection import LexicalMemoryProjection
from yisang.memory.quarantine import InMemoryQuarantinePort
from yisang.memory.sqlite import SQLiteMemoryPort


def _pipeline(memory):
    return MemoryWritePipeline(
        memory=memory,
        governor=MemoryGovernor(),
        quarantine=InMemoryQuarantinePort(),
    )


def _proposal(content, **kwargs):
    return MemoryProposal(
        content=content,
        kind="semantic",
        source_engine="test-engine",
        confidence=0.95,
        evidence=[f"evidence:{content}"],
        trust_class="verified",
        writer="governor",
        **kwargs,
    )


def test_expired_and_future_memory_are_not_active():
    now = time.time()
    expired = _proposal(
        "expired fact",
        valid_from=now - 100,
        valid_until=now - 10,
    ).to_record()
    future = _proposal(
        "future fact",
        valid_from=now + 100,
    ).to_record()

    assert expired.is_active(at=now) is False
    assert future.is_active(at=now) is False
    assert expired.is_durable is False
    assert future.is_durable is False


def test_governed_supersession_links_and_retires_old_memory():
    authoritative = InMemoryMemoryPort()
    memory = ProjectedMemoryPort(
        authoritative,
        [LexicalMemoryProjection()],
    )
    pipeline = _pipeline(memory)

    old_result = pipeline.submit(_proposal("server port is 18731"))
    assert old_result.status is MemoryWriteStatus.COMMITTED
    old = old_result.record

    new_result = pipeline.submit(
        _proposal(
            "server port is 28731",
            supersedes_id=old.memory_id,
        )
    )
    assert new_result.status is MemoryWriteStatus.COMMITTED
    new = new_result.record

    retired = authoritative.get(old.memory_id)
    assert retired is not None
    assert retired.invalidated is True
    assert retired.validation_state == "superseded"
    assert retired.superseded_by_id == new.memory_id
    assert retired.valid_until is not None
    assert new.supersedes_id == old.memory_id

    found = memory.search("server port")
    assert [record.memory_id for record in found] == [new.memory_id]
    assert [m.operation for m in memory.mutations(old.memory_id)][-1] == "supersede"


def test_supersession_rejects_missing_target():
    memory = InMemoryMemoryPort()
    result = _pipeline(memory).submit(
        _proposal(
            "replacement fact",
            supersedes_id="mem-does-not-exist",
        )
    )

    assert result.status is MemoryWriteStatus.REJECTED
    assert result.reason == "supersedes_not_found"
    assert memory.all() == []


def test_retrieval_and_outcome_tracking():
    memory = InMemoryMemoryPort()
    record = memory.commit(_proposal("retrieval usage fact"))

    assert memory.get(record.memory_id).last_used_at is None

    found = memory.search("retrieval usage")
    assert found
    after_search = memory.get(record.memory_id)
    assert after_search.last_used_at is not None

    memory.record_outcome([record.memory_id], success=True)
    memory.record_outcome([record.memory_id], success=False)
    after_outcome = memory.get(record.memory_id)

    assert after_outcome.success_count == 1
    assert after_outcome.failure_count == 1


def test_sqlite_temporal_fields_survive_reopen(tmp_path):
    path = tmp_path / "memory.db"
    first = SQLiteMemoryPort(path)
    pipeline = _pipeline(first)

    old = pipeline.submit(_proposal("dynamic state old")).record
    new = pipeline.submit(
        _proposal(
            "dynamic state new",
            supersedes_id=old.memory_id,
        )
    ).record
    first.search("dynamic state")
    first.record_outcome([new.memory_id], success=True)
    first.close()

    second = SQLiteMemoryPort(path)
    loaded_old = second.get(old.memory_id)
    loaded_new = second.get(new.memory_id)

    assert loaded_old.schema_version == MEMORY_SCHEMA_VERSION
    assert loaded_old.validation_state == "superseded"
    assert loaded_old.superseded_by_id == new.memory_id
    assert loaded_old.valid_until is not None

    assert loaded_new.supersedes_id == old.memory_id
    assert loaded_new.last_used_at is not None
    assert loaded_new.success_count == 1
    assert loaded_new.failure_count == 0
    second.close()
