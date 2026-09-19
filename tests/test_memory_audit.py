from yisang.memory.audit import audit_memory
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.memory.pipeline import MemoryWritePipeline
from yisang.memory.governor import MemoryGovernor
from yisang.memory.quarantine import InMemoryQuarantinePort


def _pipeline(memory):
    return MemoryWritePipeline(
        memory=memory,
        governor=MemoryGovernor(),
        quarantine=InMemoryQuarantinePort(),
    )


def test_audit_accepts_governed_provenance_and_supersession():
    memory = InMemoryMemoryPort()
    pipeline = _pipeline(memory)

    old = pipeline.submit(
        MemoryProposal(
            content="state old",
            source_engine="engine",
            confidence=0.95,
            evidence=["source:1"],
            trust_class="verified",
            writer="governor",
        )
    ).record
    pipeline.submit(
        MemoryProposal(
            content="state new",
            source_engine="engine",
            confidence=0.95,
            evidence=["source:2"],
            trust_class="verified",
            writer="governor",
            supersedes_id=old.memory_id,
        )
    )

    report = audit_memory(memory, require_current_schema=True)

    assert report.ok is True
    assert report.record_count == 2
    assert report.active_count == 1
    assert report.superseded_count == 1
    assert report.mutation_count == 3


def test_audit_flags_missing_provenance():
    memory = InMemoryMemoryPort()
    memory.commit(
        MemoryProposal(
            content="bad direct write",
            source_engine="unknown",
            confidence=1.0,
            evidence=[],
        )
    )

    report = audit_memory(memory)

    codes = {issue.code for issue in report.issues}
    assert report.ok is False
    assert "missing_provenance_evidence" in codes
    assert "unknown_source" in codes
