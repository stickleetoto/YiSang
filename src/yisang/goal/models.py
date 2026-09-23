from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any


GOAL_STATES = frozenset(
    {"planned", "active", "blocked", "completed", "cancelled"}
)


@dataclass(frozen=True)
class GoalBudget:
    max_attempts: int | None = None
    max_failures: int | None = None
    max_tokens: int | None = None
    max_seconds: float | None = None

    def __post_init__(self) -> None:
        for name in ("max_attempts", "max_failures", "max_tokens"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.max_seconds is not None and self.max_seconds < 0:
            raise ValueError("max_seconds must be non-negative")


@dataclass(frozen=True)
class GoalRecord:
    goal_id: str
    description: str
    state: str = "planned"
    milestones: tuple[str, ...] = ()
    completed_work: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    next_action: str | None = None
    exit_condition: str = ""
    budget: GoalBudget = field(default_factory=GoalBudget)
    provenance: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.goal_id.strip():
            raise ValueError("goal_id must be non-empty")
        if not self.description.strip():
            raise ValueError("description must be non-empty")
        if self.state not in GOAL_STATES:
            raise ValueError(f"unsupported goal state: {self.state}")
        if self.next_action is not None and not self.next_action.strip():
            raise ValueError("next_action must be non-empty when provided")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be before created_at")

    @property
    def terminal(self) -> bool:
        return self.state in {"completed", "cancelled"}
