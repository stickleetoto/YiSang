from dataclasses import dataclass

@dataclass(frozen=True)
class ContextBudgetPolicy:
    """Model-agnostic context budget.

    YiSang intentionally uses character budgets at this layer so the core
    remains independent from provider-specific tokenizers.
    """
    max_total_chars: int = 16_000
    max_user_chars: int = 4_000
    max_memory_chars: int = 8_000
    max_ego_chars: int = 3_000
    max_memories: int = 8
    max_egos: int = 3

    def __post_init__(self) -> None:
        values = (
            self.max_total_chars,
            self.max_user_chars,
            self.max_memory_chars,
            self.max_ego_chars,
            self.max_memories,
            self.max_egos,
        )
        if any(v <= 0 for v in values):
            raise ValueError("context budget values must be positive")

def trim_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[: limit - 1] + "…"
