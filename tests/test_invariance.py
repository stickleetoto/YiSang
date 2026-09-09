from yisang.eval.invariance import capture_invariance_snapshot, compare_invariance
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

def test_engine_swap_preserves_externalized_assets():
    memory = InMemoryMemoryPort()
    egos = EgoRegistry()
    egos.register(EgoManifest("ego.debug", "Debug", ("debug",), ("bug",)))

    engines = EngineRouter()
    engines.register(EchoEngine("small", "SMALL"))
    engines.register(EchoEngine("strong", "STRONG"))

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

    runtime.run(YiSangRequest("r1", "remember: stable identity"))
    before = capture_invariance_snapshot(runtime)

    runtime.state.active_engine = "strong"
    after = capture_invariance_snapshot(runtime)

    result = compare_invariance(before, after)
    assert all(result.values())
