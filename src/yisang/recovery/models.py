from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any


RUN_EVENT_TYPES = frozenset(
    {
        "goal_started",
        "step_planned",
        "action_proposed",
        "action_authorized",
        "action_executed",
        "verification_result",
        "checkpoint_written",
        "blocker_detected",
        "goal_completed",
        "goal_cancelled",
        "side_effect_reserved",
        "side_effect_committed",
        "side_effect_failed",
        "recovery_decision",
    }
)

SIDE_EFFECT_RECEIPT_STATES = frozenset({"started", "committed", "failed"})
RECOVERY_ACTION_DECISIONS = frozenset({"execute", "skip", "review", "retry"})


@dataclass(frozen=True)
class RunJournalEvent:
    event_id: str
    goal_id: str
    run_id: str
    sequence: int
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id must be non-empty")
        if not self.goal_id.strip():
            raise ValueError("goal_id must be non-empty")
        if not self.run_id.strip():
            raise ValueError("run_id must be non-empty")
        if self.sequence <= 0:
            raise ValueError("sequence must be positive")
        if self.event_type not in RUN_EVENT_TYPES:
            raise ValueError(
                f"unsupported run journal event: {self.event_type}"
            )


@dataclass(frozen=True)
class RecoveryCheckpoint:
    checkpoint_id: str
    goal_id: str
    run_id: str
    journal_sequence: int
    goal_state: str
    next_action: str | None
    completed_action_refs: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.checkpoint_id.strip():
            raise ValueError("checkpoint_id must be non-empty")
        if not self.goal_id.strip():
            raise ValueError("goal_id must be non-empty")
        if not self.run_id.strip():
            raise ValueError("run_id must be non-empty")
        if self.journal_sequence < 0:
            raise ValueError("journal_sequence must be non-negative")


@dataclass(frozen=True)
class RecoveryPlan:
    goal_id: str
    run_id: str | None
    checkpoint_id: str | None
    resume_allowed: bool
    reason: str
    goal_state: str
    next_action: str | None
    completed_action_refs: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    journal_sequence: int = 0



@dataclass(frozen=True)
class SideEffectReceipt:
    receipt_id: str
    goal_id: str
    run_id: str
    idempotency_key: str
    tool_id: str
    request_digest: str
    state: str = "started"
    result_ref: str | None = None
    evidence_refs: tuple[str, ...] = ()
    failure_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.receipt_id.strip():
            raise ValueError("receipt_id must be non-empty")
        if not self.goal_id.strip():
            raise ValueError("goal_id must be non-empty")
        if not self.run_id.strip():
            raise ValueError("run_id must be non-empty")
        if not self.idempotency_key.strip():
            raise ValueError("idempotency_key must be non-empty")
        if not self.tool_id.strip():
            raise ValueError("tool_id must be non-empty")
        if not self.request_digest.strip():
            raise ValueError("request_digest must be non-empty")
        if self.state not in SIDE_EFFECT_RECEIPT_STATES:
            raise ValueError(
                f"unsupported side-effect receipt state: {self.state}"
            )
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot be before created_at")


@dataclass(frozen=True)
class RecoveryActionDecision:
    goal_id: str
    idempotency_key: str
    decision: str
    reason: str
    receipt_id: str | None = None
    receipt_state: str | None = None

    def __post_init__(self) -> None:
        if self.decision not in RECOVERY_ACTION_DECISIONS:
            raise ValueError(
                f"unsupported recovery action decision: {self.decision}"
            )
