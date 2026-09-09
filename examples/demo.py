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

identity = IdentityCharter(agent_id="yisang-001", name="YiSang")
state = AgentState(active_engine="qwen-demo", active_project="YiSang")

memory = InMemoryMemoryPort()
governor = MemoryGovernor()

egos = EgoRegistry()
egos.register(EgoManifest(
    ego_id="ego.python.debug",
    name="Python Debugger",
    provides=("python_debugging",),
    keywords=("python", "pytest", "traceback", "버그"),
    instructions="Inspect evidence, isolate the failing behavior, verify with tests.",
))
egos.register(EgoManifest(
    ego_id="ego.repo.inspect",
    name="Repository Inspector",
    provides=("repository_analysis",),
    keywords=("repo", "repository", "레포", "저장소"),
    instructions="Inspect structure before changing implementation.",
))

engines = EngineRouter()
engines.register(EchoEngine("qwen-demo", "SMALL"))
engines.register(EchoEngine("codex-demo", "STRONG"))

runtime = YiSangRuntime(
    identity=identity,
    state=state,
    memory=memory,
    governor=governor,
    ego_registry=egos,
    capability_router=CapabilityRouter(),
    context_compiler=ContextCompiler(),
    engine_router=engines,
    verifier=PassThroughVerifier(),
)

print(runtime.run(YiSangRequest("req-1", "remember: YiSang keeps memory outside the model")).text)

state.active_engine = "codex-demo"

result = runtime.run(YiSangRequest("req-2", "repo python 버그를 분석해"))
print(result.text)
print("engine:", result.engine_id)
print("memory:", [m.content for m in memory.all()])
print("E.G.O:", result.used_ego_ids)
