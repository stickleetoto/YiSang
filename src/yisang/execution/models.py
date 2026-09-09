from dataclasses import dataclass, field
from typing import Any


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


@dataclass
class ActionResult:
    tool_id: str
    status: str
    output: Any = None
    error: str | None = None
    gate_reason: str = ""
    ego_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "gate_reason": self.gate_reason,
            "ego_id": self.ego_id,
        }
