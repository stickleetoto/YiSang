from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BioProviderConfig:
    project: str | None = None
    namespace: str | None = None
    proposed_by: str = "yisang"
    source_prefix: str = "yisang"
    default_limit: int = 8
    context_char_budget: int = 2400

    def __post_init__(self) -> None:
        if not self.proposed_by.strip():
            raise ValueError("proposed_by must be non-empty")
        if not self.source_prefix.strip():
            raise ValueError("source_prefix must be non-empty")
        if self.default_limit <= 0:
            raise ValueError("default_limit must be positive")
        if self.context_char_budget <= 0:
            raise ValueError("context_char_budget must be positive")
