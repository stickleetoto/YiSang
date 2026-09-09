from yisang.core.models import YiSangRequest
from yisang.core.runtime import YiSangRuntime
from yisang.identity.models import IdentityCharter, AgentState
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.governor import MemoryGovernor
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.context.compiler import ContextCompiler
from yisang.engines.router import EngineRouter
from yisang.engines.demo import EchoEngine
from yisang.verification.base import PassThroughVerifier

def build_runtime():
    identity = IdentityCharter(agent_id="yisang-001", name="YiSang")
    state = AgentState(active_engine="small")
    memory = InMemoryMemoryPort()
    engines = EngineRouter()
    engines.register(EchoEngine("small", "SMALL"))
    engines.register(EchoEngine("strong", "STRONG"))

    return YiSangRuntime(
        identity=identity,
        state=state,
        memory=memory,
        governor=MemoryGovernor(),
        ego_registry=EgoRegistry(),
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
        verifier=PassThroughVerifier(),
    )

def test_engine_swap_preserves_memory_and_identity():
    runtime = build_runtime()

    runtime.run(YiSangRequest("r1", "remember: engine swaps must preserve memory"))
    assert len(runtime.memory.all()) == 1
    assert runtime.identity.agent_id == "yisang-001"

    runtime.state.active_engine = "strong"
    response = runtime.run(YiSangRequest("r2", "engine swap check"))

    assert response.engine_id == "strong"
    assert len(runtime.memory.all()) == 1
    assert runtime.identity.agent_id == "yisang-001"
