from yisang.context.compiler import ContextCompiler
from yisang.core.models import YiSangRequest
from yisang.core.runtime import YiSangRuntime
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.base import EngineResult, LLMEngine
from yisang.engines.router import EngineRouter
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.memory.pipeline import MemoryWritePipeline, MemoryWriteStatus
from yisang.memory.quarantine import InMemoryQuarantinePort
from yisang.verification.base import PassThroughVerifier


def test_untrusted_memory_is_quarantined_not_committed():
    memory = InMemoryMemoryPort()
    quarantine = InMemoryQuarantinePort()
    pipeline = MemoryWritePipeline(
        memory=memory,
        governor=MemoryGovernor(),
        quarantine=quarantine,
    )

    result = pipeline.submit(
        MemoryProposal(
            content="run an unrelated command later",
            confidence=0.95,
            evidence=["external:web"],
            trust_class="untrusted",
        )
    )

    assert result.status is MemoryWriteStatus.QUARANTINED
    assert result.quarantine is not None
    assert memory.all() == []
    assert len(quarantine.all()) == 1


def test_quarantined_memory_can_be_released_after_review():
    memory = InMemoryMemoryPort()
    quarantine = InMemoryQuarantinePort()
    pipeline = MemoryWritePipeline(
        memory=memory,
        governor=MemoryGovernor(),
        quarantine=quarantine,
    )
    initial = pipeline.submit(
        MemoryProposal(
            content="verified after manual review",
            confidence=0.95,
            evidence=["external:source"],
            trust_class="untrusted",
        )
    )

    released = pipeline.release(
        initial.quarantine.quarantine_id,
        reviewer="reviewer-1",
        trust_class="verified",
        additional_evidence=("review:ticket-1",),
    )

    assert released.status is MemoryWriteStatus.COMMITTED
    assert released.record is not None
    assert released.record.trust_class == "verified"
    assert released.record.writer == "reviewer-1"
    assert "review:ticket-1" in released.record.evidence_refs
    assert quarantine.all() == []
    assert len(memory.all()) == 1


def test_rejected_memory_does_not_enter_quarantine():
    memory = InMemoryMemoryPort()
    quarantine = InMemoryQuarantinePort()
    pipeline = MemoryWritePipeline(
        memory=memory,
        governor=MemoryGovernor(),
        quarantine=quarantine,
    )

    result = pipeline.submit(
        MemoryProposal(
            content="low confidence claim",
            confidence=0.1,
            evidence=["weak:signal"],
        )
    )

    assert result.status is MemoryWriteStatus.REJECTED
    assert result.reason == "confidence_below_threshold"
    assert quarantine.all() == []
    assert memory.all() == []


class UntrustedMemoryEngine(LLMEngine):
    engine_id = "untrusted-memory-engine"

    def generate(self, context):
        return EngineResult(
            engine_id=self.engine_id,
            text="done",
            memory_proposals=[
                MemoryProposal(
                    content="external instruction pretending to be durable memory",
                    confidence=0.95,
                    evidence=["tool-output:1"],
                    trust_class="untrusted",
                )
            ],
        )


def test_runtime_routes_verified_proposals_through_pipeline():
    memory = InMemoryMemoryPort()
    quarantine = InMemoryQuarantinePort()
    governor = MemoryGovernor()
    pipeline = MemoryWritePipeline(
        memory=memory,
        governor=governor,
        quarantine=quarantine,
    )
    engines = EngineRouter()
    engines.register(UntrustedMemoryEngine())

    runtime = YiSangRuntime(
        identity=IdentityCharter("yisang-001", "YiSang"),
        state=AgentState(active_engine="untrusted-memory-engine"),
        memory=memory,
        governor=governor,
        ego_registry=EgoRegistry(),
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
        verifier=PassThroughVerifier(),
        memory_pipeline=pipeline,
    )

    response = runtime.run(YiSangRequest("req-1", "test memory write"))

    assert response.verification_status == "PASS"
    assert response.memory_write_results[0]["status"] == "quarantined"
    assert response.memory_write_results[0]["quarantine_id"]
    assert memory.all() == []
    assert len(quarantine.all()) == 1
