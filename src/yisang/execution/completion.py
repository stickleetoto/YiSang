from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolOutcome:
    """Tool handler result with an optional deterministic goal-completion signal.

    Tool handlers may return a plain value for legacy behavior. Returning
    ToolOutcome lets deterministic code state that the requested effect is
    already satisfied, allowing the runtime to stop before another model turn.
    """

    output: Any = None
    goal_satisfied: bool = False
    completion_text: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.completion_text is not None and not self.completion_text.strip():
            raise ValueError("completion_text must be non-empty when provided")
        if self.completion_text is not None and not self.goal_satisfied:
            raise ValueError(
                "completion_text requires goal_satisfied=True"
            )
