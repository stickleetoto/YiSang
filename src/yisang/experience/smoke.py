from __future__ import annotations
import argparse,json
from pathlib import Path
from yisang.context.compiler import ContextCompiler
from yisang.core.models import YiSangRequest
from yisang.core.runtime import YiSangRuntime
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.demo import EchoEngine
from yisang.engines.router import EngineRouter
from yisang.identity.models import AgentState,IdentityCharter
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.verification.base import PassThroughVerifier
from .episode_sqlite import SQLiteExperiencePort

def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="yisang-experience-smoke")
    p.add_argument("--db",default="artifacts/experience-v07-smoke.db")
    a=p.parse_args(argv); db=Path(a.db); db.parent.mkdir(parents=True,exist_ok=True)
    if db.exists(): db.unlink()
    engines=EngineRouter(); engines.register(EchoEngine("smoke-engine","SMOKE"))
    with SQLiteExperiencePort(db) as experience:
      runtime=YiSangRuntime(
        identity=IdentityCharter("yisang-smoke","YiSang"),state=AgentState(active_engine="smoke-engine"),
        memory=InMemoryMemoryPort(),governor=MemoryGovernor(),ego_registry=EgoRegistry(),
        capability_router=CapabilityRouter(),context_compiler=ContextCompiler(),
        engine_router=engines,verifier=PassThroughVerifier(),experience_port=experience,
      )
      response=runtime.run(YiSangRequest("v07-smoke","exercise the experience capture path",{
        "experience_summary":"v0.7 local runtime smoke","experience_triggers":["local smoke"]
      }))
      eid=response.experience_episode_id
    with SQLiteExperiencePort(db) as reopened: episodes=reopened.list_episodes()
    raw="exercise the experience capture path"
    stored=json.dumps([{"summary":e.summary,"metadata":e.metadata} for e in episodes],ensure_ascii=False)
    payload={
      "ready":response.verification_status=="PASS" and eid is not None and len(episodes)==1 and episodes[0].episode_id==eid,
      "db":str(db),"verification_status":response.verification_status,
      "experience_episode_id":eid,"episode_count_after_reopen":len(episodes),
      "outcome":episodes[0].outcome if episodes else None,"raw_request_stored":raw in stored,
    }
    print(json.dumps(payload,ensure_ascii=False,indent=2))
    return 0 if payload["ready"] and not payload["raw_request_stored"] else 1

if __name__=="__main__": raise SystemExit(main())
