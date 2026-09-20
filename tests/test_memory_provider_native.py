from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.memory.native_provider import NativeMemoryProvider
from yisang.memory.pipeline import MemoryWritePipeline
from yisang.memory.quarantine import InMemoryQuarantinePort


def _provider():
    memory = InMemoryMemoryPort()
    pipeline = MemoryWritePipeline(
        memory=memory,
        governor=MemoryGovernor(),
        quarantine=InMemoryQuarantinePort(),
    )
    return NativeMemoryProvider(memory=memory, pipeline=pipeline)


def test_native_provider_preserves_governed_write_path():
    provider = _provider()
    result = provider.remember(
        MemoryProposal(
            content="SQLite is current.",
            confidence=0.9,
            evidence=["user:1"],
            trust_class="trusted",
        )
    )
    assert result.status == "committed"
    assert result.record is not None
    assert provider.recall("SQLite")[0].memory_id == result.record.memory_id


def test_native_provider_context_is_budget_bounded():
    provider = _provider()
    provider.remember(
        MemoryProposal(
            content="A" * 100,
            confidence=0.9,
            evidence=["user:1"],
            trust_class="trusted",
        )
    )
    context = provider.get_context("AAAA", char_budget=25)
    assert len(context.text) <= 25
