from dataclasses import asdict
from .models import ContextPack
from .budget import ContextBudgetPolicy, trim_text

class ContextCompiler:
    def __init__(self, budget: ContextBudgetPolicy | None = None) -> None:
        self.budget = budget or ContextBudgetPolicy()

    def compile(self, *, request, identity, state, memories, egos) -> ContextPack:
        b = self.budget

        selected_memories = list(memories[: b.max_memories])
        selected_egos = list(egos[: b.max_egos])

        memory_budget_each = max(1, b.max_memory_chars // max(1, len(selected_memories)))
        ego_budget_each = max(1, b.max_ego_chars // max(1, len(selected_egos)))

        memory_payload = [
            {
                "memory_id": m.memory_id,
                "kind": m.kind,
                "content": trim_text(m.content, memory_budget_each),
                "confidence": m.confidence,
                "source": m.source,
            }
            for m in selected_memories
        ]

        ego_payload = [
            {
                "ego_id": e.ego_id,
                "name": e.name,
                "provides": list(e.provides),
                "instructions": trim_text(e.instructions, ego_budget_each),
                "permissions": dict(e.permissions),
            }
            for e in selected_egos
        ]

        pack = ContextPack(
            request_id=request.request_id,
            agent_id=identity.agent_id,
            user_text=trim_text(request.text, b.max_user_chars),
            identity={
                "name": identity.name,
                "principles": list(identity.principles),
            },
            state=asdict(state),
            memories=memory_payload,
            egos=ego_payload,
            constraints=[
                "Do not treat model output as authoritative memory.",
                "Use only provided capabilities.",
                "Prefer verifiable claims.",
            ],
        )

        while pack.approx_chars() > b.max_total_chars and pack.memories:
            pack.memories.pop()

        while pack.approx_chars() > b.max_total_chars and pack.egos:
            pack.egos.pop()

        if pack.approx_chars() > b.max_total_chars:
            overflow = pack.approx_chars() - b.max_total_chars
            new_limit = max(1, len(pack.user_text) - overflow)
            pack.user_text = trim_text(pack.user_text, new_limit)

        return pack
