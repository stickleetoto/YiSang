from yisang.context.compiler import ContextCompiler
from yisang.core.models import YiSangRequest
from yisang.core.runtime import YiSangRuntime
from yisang.ego.models import EgoManifest
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.base import EngineResult, LLMEngine
from yisang.engines.router import EngineRouter
from yisang.execution.models import ActionProposal
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.verification.action import ActionEvidenceVerifier
from yisang.verification.base import PassThroughVerifier
from yisang.verification.composite import CompositeVerifier


def test_action_verifier_accepts_executed_evidence():
    result = EngineResult(
        "engine",
        "ok",
        metadata={"action_results": [{"tool_id": "x", "status": "EXECUTED"}]},
    )
    verdict = ActionEvidenceVerifier().verify(request=None, engine_result=result)
    assert verdict.status == "PASS"


def test_action_verifier_fails_denied_action():
    result = EngineResult(
        "engine",
        "ok",
        metadata={"action_results": [{"tool_id": "x", "status": "DENIED"}]},
    )
    verdict = ActionEvidenceVerifier().verify(request=None, engine_result=result)
    assert verdict.status == "FAIL"
    assert verdict.reason == "action_denied:x"


def test_composite_verifier_runs_both_checks():
    result = EngineResult(
        "engine",
        "ok",
        metadata={"action_results": [{"tool_id": "x", "status": "EXECUTED"}]},
    )
    verifier = CompositeVerifier([PassThroughVerifier(), ActionEvidenceVerifier()])
    verdict = verifier.verify(request=None, engine_result=result)
    assert verdict.status == "PASS"
    assert "ActionEvidenceVerifier:actions_verified" in verdict.reason


class DeniedMemoryEngine(LLMEngine):
    engine_id = "denied-memory"

    def generate(self, context):
        return EngineResult(
            engine_id=self.engine_id,
            text="I changed it",
            memory_proposals=[
                MemoryProposal(
                    content="change succeeded",
                    confidence=0.95,
                    evidence=["engine-claim"],
                )
            ],
            action_proposals=[ActionProposal("missing.tool")],
        )


def test_denied_action_prevents_memory_commit():
    egos = EgoRegistry()
    egos.register(
        EgoManifest(
            ego_id="ego.repo",
            name="Repo",
            provides=("repository_analysis",),
            keywords=("repo",),
        )
    )
    engines = EngineRouter()
    engines.register(DeniedMemoryEngine())
    memory = InMemoryMemoryPort()

    runtime = YiSangRuntime(
        identity=IdentityCharter("yisang-001", "YiSang"),
        state=AgentState(active_engine="denied-memory"),
        memory=memory,
        governor=MemoryGovernor(),
        ego_registry=egos,
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
        verifier=CompositeVerifier([PassThroughVerifier(), ActionEvidenceVerifier()]),
        action_runtime=None,
    )

    response = runtime.run(YiSangRequest("r", "repo change"))
    assert response.verification_status == "FAIL"
    assert memory.all() == []
