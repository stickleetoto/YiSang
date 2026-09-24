from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any


PLAN_STATES = frozenset(
    {"active", "blocked", "completed", "cancelled", "superseded"}
)
PLAN_STEP_STATES = frozenset(
    {"pending", "running", "completed", "failed", "blocked"}
)
PLAN_EXECUTION_DECISIONS = frozenset(
    {
        "start_step",
        "retry_step",
        "wait",
        "completed",
        "replan_required",
        "stop",
    }
)


@dataclass(frozen=True)
class PlanStepSpec:
    step_id: str
    title: str
    description: str = ""
    depends_on: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    verification: str = ""
    max_attempts: int = 1
    priority: int = 0

    def __post_init__(self) -> None:
        if not self.step_id.strip():
            raise ValueError("step_id must be non-empty")
        if not self.title.strip():
            raise ValueError("title must be non-empty")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if self.step_id in self.depends_on:
            raise ValueError("step cannot depend on itself")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("depends_on must not contain duplicates")


@dataclass(frozen=True)
class PlanProposal:
    proposal_id: str
    plan_id: str
    goal_id: str
    steps: tuple[PlanStepSpec, ...]
    proposed_by: str
    provenance: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.proposal_id.strip():
            raise ValueError("proposal_id must be non-empty")
        if not self.plan_id.strip():
            raise ValueError("plan_id must be non-empty")
        if not self.goal_id.strip():
            raise ValueError("goal_id must be non-empty")
        if not self.proposed_by.strip():
            raise ValueError("proposed_by must be non-empty")
        if not self.steps:
            raise ValueError("plan proposal requires at least one step")


@dataclass(frozen=True)
class PlanStep:
    step_id: str
    title: str
    description: str
    ordinal: int
    depends_on: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    verification: str = ""
    max_attempts: int = 1
    priority: int = 0
    state: str = "pending"
    attempt_count: int = 0
    result_ref: str | None = None
    evidence_refs: tuple[str, ...] = ()
    blocker: str | None = None
    last_error: str | None = None

    def __post_init__(self) -> None:
        if not self.step_id.strip():
            raise ValueError("step_id must be non-empty")
        if not self.title.strip():
            raise ValueError("title must be non-empty")
        if self.ordinal < 0:
            raise ValueError("ordinal must be non-negative")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if self.attempt_count < 0:
            raise ValueError("attempt_count must be non-negative")
        if self.state not in PLAN_STEP_STATES:
            raise ValueError(f"unsupported plan step state: {self.state}")


@dataclass(frozen=True)
class GoalPlan:
    plan_id: str
    goal_id: str
    revision: int
    state: str
    steps: tuple[PlanStep, ...]
    provenance: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.plan_id.strip():
            raise ValueError("plan_id must be non-empty")
        if not self.goal_id.strip():
            raise ValueError("goal_id must be non-empty")
        if self.revision <= 0:
            raise ValueError("revision must be positive")
        if self.state not in PLAN_STATES:
            raise ValueError(f"unsupported plan state: {self.state}")
        if not self.steps:
            raise ValueError("plan requires at least one step")
        step_ids = tuple(step.step_id for step in self.steps)
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("plan step ids must be unique")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be before created_at")

    @property
    def terminal(self) -> bool:
        return self.state in {"completed", "cancelled", "superseded"}


@dataclass(frozen=True)
class PlanExecutionDecision:
    plan_id: str
    revision: int
    decision: str
    reason: str
    step_id: str | None = None

    def __post_init__(self) -> None:
        if self.decision not in PLAN_EXECUTION_DECISIONS:
            raise ValueError(
                f"unsupported plan execution decision: {self.decision}"
            )
