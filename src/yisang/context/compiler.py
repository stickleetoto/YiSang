from dataclasses import asdict
from .models import ContextPack

class ContextCompiler:
    def compile(self, *, request, identity, state, memories, egos) -> ContextPack:
        return ContextPack(
            request_id=request.request_id,
            agent_id=identity.agent_id,
            user_text=request.text,
            identity={
                "name": identity.name,
                "principles": list(identity.principles),
            },
            state=asdict(state),
            memories=[
                {
                    "memory_id": m.memory_id,
                    "kind": m.kind,
                    "content": m.content,
                    "confidence": m.confidence,
                }
                for m in memories
            ],
            egos=[
                {
                    "ego_id": e.ego_id,
                    "name": e.name,
                    "provides": list(e.provides),
                    "instructions": e.instructions,
                }
                for e in egos
            ],
            constraints=[
                "Do not treat model output as authoritative memory.",
                "Use only provided capabilities.",
                "Prefer verifiable claims.",
            ],
        )
