from yisang.core.models import YiSangRequest
from yisang.core.runtime import YiSangRuntime
from yisang.identity.models import IdentityCharter, AgentState
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.governor import MemoryGovernor
from yisang.ego.models import EgoManifest
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.context.compiler import ContextCompiler
from yisang.engines.router import EngineRouter
from yisang.engines.demo import EchoEngine
from yisang.verification.base import PassThroughVerifier

def test_runtime_uses_memory_and_ego():
    memory = InMemoryMemoryPort()
    memory.commit(__import__("yisang.memory.models", fromlist=["MemoryProposal"]).MemoryProposal(
        content="python repository uses pytest",
        confidence=1.0,
        evidence=["seed"],
    ))

    egos = EgoRegistry()
    egos.register(EgoManifest(
        ego_id="ego.python.debug",
        name="Python Debugger",
        provides=("python_debugging",),
        keywords=("python", "pytest"),
    ))

    engines = EngineRouter()
    engines.register(EchoEngine("small", "SMALL"))

    runtime = YiSangRuntime(
        identity=IdentityCharter("yisang-001", "YiSang"),
        state=AgentState(active_engine="small"),
        memory=memory,
        governor=MemoryGovernor(),
        ego_registry=egos,
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
        verifier=PassThroughVerifier(),
    )

    response = runtime.run(YiSangRequest("r", "python pytest 문제"))
    assert response.used_memory_ids
    assert response.used_ego_ids == ["ego.python.debug"]
    assert response.verification_status == "PASS"
