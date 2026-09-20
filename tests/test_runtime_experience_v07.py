from yisang.context.compiler import ContextCompiler
from yisang.core.models import YiSangRequest
from yisang.core.runtime import YiSangRuntime
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.demo import EchoEngine
from yisang.engines.router import EngineRouter
from yisang.experience import InMemoryExperiencePort
from yisang.identity.models import AgentState,IdentityCharter
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.verification.base import PassThroughVerifier

def test_runtime_captures_normalized_experience_episode():
    engines=EngineRouter(); engines.register(EchoEngine("small","SMALL")); xp=InMemoryExperiencePort()
    runtime=YiSangRuntime(identity=IdentityCharter("id","YiSang"),state=AgentState(active_engine="small"),memory=InMemoryMemoryPort(),governor=MemoryGovernor(),ego_registry=EgoRegistry(),capability_router=CapabilityRouter(),context_compiler=ContextCompiler(),engine_router=engines,verifier=PassThroughVerifier(),experience_port=xp)
    raw="private raw text"
    response=runtime.run(YiSangRequest("req",raw,{"experience_summary":"runtime capture","experience_triggers":["integration"]}))
    assert response.experience_episode_id
    e=xp.get_episode(response.experience_episode_id)
    assert e and e.outcome=="success" and e.summary=="runtime capture"
    assert e.trigger_conditions==("integration",) and raw not in repr(e.metadata)
