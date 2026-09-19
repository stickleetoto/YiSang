from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.memory.pipeline import MemoryWritePipeline, MemoryWriteStatus
from yisang.memory.quarantine_sqlite import SQLiteQuarantinePort


def test_sqlite_quarantine_survives_reopen(tmp_path):
    path = tmp_path / "quarantine.db"
    first = SQLiteQuarantinePort(path)

    item = first.put(
        MemoryProposal(
            content="untrusted memory candidate",
            confidence=0.95,
            evidence=["external:source"],
            trust_class="untrusted",
            source_id="turn-1",
            source_type="tool_output",
            metadata={"k": "v"},
        ),
        reason="untrusted_requires_quarantine",
        risk_flags=("untrusted_source",),
        metadata={"review": "pending"},
    )
    first.close()

    second = SQLiteQuarantinePort(path)
    loaded = second.get(item.quarantine_id)

    assert loaded is not None
    assert loaded.proposal.content == "untrusted memory candidate"
    assert loaded.proposal.source_id == "turn-1"
    assert loaded.proposal.source_type == "tool_output"
    assert loaded.proposal.metadata == {"k": "v"}
    assert loaded.reason == "untrusted_requires_quarantine"
    assert loaded.risk_flags == ("untrusted_source",)
    assert loaded.metadata == {"review": "pending"}
    second.close()


def test_pipeline_can_release_persistent_quarantine(tmp_path):
    memory = InMemoryMemoryPort()
    quarantine = SQLiteQuarantinePort(tmp_path / "quarantine.db")
    pipeline = MemoryWritePipeline(
        memory=memory,
        governor=MemoryGovernor(),
        quarantine=quarantine,
    )

    initial = pipeline.submit(
        MemoryProposal(
            content="candidate that needs review",
            confidence=0.9,
            evidence=["external:one"],
            trust_class="untrusted",
        )
    )

    assert initial.status is MemoryWriteStatus.QUARANTINED

    released = pipeline.release(
        initial.quarantine.quarantine_id,
        reviewer="reviewer-1",
        trust_class="verified",
    )

    assert released.status is MemoryWriteStatus.COMMITTED
    assert len(memory.all()) == 1
    assert quarantine.all() == []
    quarantine.close()


def test_sqlite_quarantine_remove_is_idempotent(tmp_path):
    quarantine = SQLiteQuarantinePort(tmp_path / "quarantine.db")
    item = quarantine.put(
        MemoryProposal(
            content="remove me",
            confidence=1.0,
            evidence=["test"],
            trust_class="untrusted",
        ),
        reason="test",
    )

    removed = quarantine.remove(item.quarantine_id)

    assert removed is not None
    assert removed.quarantine_id == item.quarantine_id
    assert quarantine.remove(item.quarantine_id) is None
    quarantine.close()
