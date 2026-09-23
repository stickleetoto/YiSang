from dataclasses import dataclass, field
from typing import Any

from .failure import ToolFailure


@dataclass(frozen=True)
class ActionProposal:
    """A model-proposed tool invocation.

    `action` is the stable tool id. Engines may propose actions, but only the
    YiSang execution layer may authorize and run them.
    """

    action: str
    arguments: dict[str, Any] = field(default_factory=dict)
    requested_by: str | None = None


@dataclass(frozen=True)
class ActionDecision:
    tool_id: str
    allowed: bool
    reason: str
    ego_id: str | None = None
    policy_reason: str | None = None
    policy_rule_ids: tuple[str, ...] = ()


@dataclass
class ActionResult:
    tool_id: str
    status: str
    output: Any = None
    error: str | None = None
    gate_reason: str = ""
    ego_id: str | None = None
    failure: ToolFailure | None = None
    goal_satisfied: bool = False
    completion_text: str | None = None
    completion_evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "gate_reason": self.gate_reason,
            "ego_id": self.ego_id,
            "failure": self.failure.to_dict() if self.failure is not None else None,
            "goal_satisfied": self.goal_satisfied,
            "completion_text": self.completion_text,
            "completion_evidence": dict(self.completion_evidence),
        }
