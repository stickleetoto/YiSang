from __future__ import annotations
from hashlib import sha256
from typing import Any
import uuid
from .models import ExperienceEpisode, ExperienceEvidence

class ExperienceRecorder:
    """Normalize completed runtime turns without copying raw request text."""

    def capture(self,*,request_id:str,request_text:str,request_metadata:dict[str,Any],
                engine_id:str,verification_status:str,verification_reason:str,
                action_results:list[Any],memories:list[Any],
                library_payload:tuple[dict,...]|list[dict])->ExperienceEpisode:
        evidence=[
            ExperienceEvidence(f"request:{request_id}","raw_conversation","runtime request captured",False),
            ExperienceEvidence(
                f"verification:{request_id}","verification_result",
                f"verification={verification_status}"+(f" reason={verification_reason}" if verification_reason else ""),
                verification_status=="PASS",
            ),
        ]
        steps=[]; action_failed=False; goal_verified=False
        for i,result in enumerate(action_results):
            status=str(getattr(result,"status","")); tool_id=str(getattr(result,"tool_id","unknown"))
            goal=bool(getattr(result,"goal_satisfied",False))
            if status=="EXECUTED": steps.append(f"tool:{tool_id}")
            else: action_failed=True
            goal_verified=goal_verified or (status=="EXECUTED" and goal)
            evidence.append(ExperienceEvidence(
                f"tool:{request_id}:{i}:{tool_id}","tool_result",
                f"tool={tool_id} status={status} goal_satisfied={str(goal).lower()}",
                status=="EXECUTED" and goal,
            ))
        for memory in memories:
            mid=str(getattr(memory,"memory_id","")).strip()
            if not mid: continue
            trust=str(getattr(memory,"trust_class","unknown"))
            state=str(getattr(memory,"validation_state","committed"))
            evidence.append(ExperienceEvidence(
                f"memory:{mid}","governed_memory",f"memory={mid} trust={trust} state={state}",
                trust in {"trusted","verified"} and state=="committed",
            ))
        for item in library_payload:
            ref=str(item.get("knowledge_ref","")).strip()
            if not ref: continue
            trust=str(item.get("trust_class","unknown")); state=str(item.get("validation_state","unknown"))
            evidence.append(ExperienceEvidence(
                f"library:{ref}","library_ref",f"knowledge={ref} trust={trust} state={state}",
                trust=="verified" and state in {"validated","promoted"},
            ))
        success=verification_status=="PASS" and not action_failed
        val=request_metadata.get("experience_summary")
        summary=val.strip()[:500] if isinstance(val,str) and val.strip() else f"runtime turn {request_id} {'succeeded' if success else 'failed'} on {engine_id}"
        tv=request_metadata.get("experience_triggers",())
        if isinstance(tv,str): triggers=(tv.strip(),) if tv.strip() else ()
        elif isinstance(tv,(list,tuple)): triggers=tuple(str(x).strip() for x in tv if str(x).strip())
        else: triggers=()
        return ExperienceEpisode(
            episode_id=f"episode-{uuid.uuid4().hex[:12]}",
            outcome="success" if success else "failure",summary=summary,evidence=tuple(evidence),
            trigger_conditions=triggers,procedure_steps=tuple(steps),
            request_id=request_id,engine_id=engine_id,verification_status=verification_status,
            metadata={
                "request_sha256":sha256(request_text.encode("utf-8")).hexdigest(),
                "verification_reason":verification_reason,
                "action_count":len(action_results),"goal_verified":goal_verified,
            },
        )
