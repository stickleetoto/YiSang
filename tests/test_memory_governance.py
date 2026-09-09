from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.governor import MemoryGovernor
from yisang.memory.models import MemoryProposal

def test_memory_requires_evidence():
    memory = InMemoryMemoryPort()
    governor = MemoryGovernor()

    proposal = MemoryProposal(
        content="hello",
        confidence=0.9,
        evidence=[],
    )
    assert not governor.evaluate(proposal, memory).accepted

def test_memory_commit_after_governance():
    memory = InMemoryMemoryPort()
    governor = MemoryGovernor()

    proposal = MemoryProposal(
        content="YiSang keeps memory outside the model",
        confidence=0.9,
        evidence=["test"],
    )

    decision = governor.evaluate(proposal, memory)
    assert decision.accepted
    memory.commit(proposal)
    assert len(memory.all()) == 1
