from .base import LLMEngine, EngineResult
from yisang.memory.models import MemoryProposal

class EchoEngine(LLMEngine):
    def __init__(self, engine_id: str, intelligence_label: str) -> None:
        self.engine_id = engine_id
        self.intelligence_label = intelligence_label

    def generate(self, context) -> EngineResult:
        mem_count = len(context.memories)
        ego_count = len(context.egos)
        text = (
            f"[{self.intelligence_label}] "
            f"{context.identity['name']} responding with "
            f"{mem_count} memories and {ego_count} E.G.O modules: "
            f"{context.user_text}"
        )

        proposals = []
        if "remember:" in context.user_text.lower():
            content = context.user_text.split(":", 1)[1].strip()
            proposals.append(
                MemoryProposal(
                    content=content,
                    kind="semantic",
                    source_engine=self.engine_id,
                    confidence=0.95,
                    evidence=[f"user-request:{context.request_id}"],
                )
            )

        return EngineResult(
            engine_id=self.engine_id,
            text=text,
            memory_proposals=proposals,
        )
