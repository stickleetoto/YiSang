from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ToolFailureCategory(str, Enum):
    INVALID_ARGUMENTS = "invalid_arguments"
    PERMISSION = "permission"
    ENVIRONMENT = "environment"
    TRANSIENT = "transient"
    EXECUTION = "execution"
    TIMEOUT = "timeout"
    VERIFICATION = "verification"


@dataclass(frozen=True)
class ToolFailure:
    category: ToolFailureCategory
    retryable: bool
    blame: str
    recovery_hint: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "retryable": self.retryable,
            "blame": self.blame,
            "recovery_hint": self.recovery_hint,
            "evidence": dict(self.evidence),
        }


def failure_from_gate_reason(reason: str, *, tool_id: str) -> ToolFailure:
    if reason == "unknown_tool":
        return ToolFailure(
            ToolFailureCategory.INVALID_ARGUMENTS,
            retryable=True,
            blame="model",
            recovery_hint="Choose one of the currently exposed tools.",
            evidence={"tool_id": tool_id, "gate_reason": reason},
        )
    if reason in {
        "side_effects_disabled",
        "insufficient_permission",
        "missing_capability",
        "policy_denied",
        "policy_no_permit",
    }:
        return ToolFailure(
            ToolFailureCategory.PERMISSION,
            retryable=False,
            blame="policy",
            recovery_hint="Request or select an authorized capability before retrying.",
            evidence={"tool_id": tool_id, "gate_reason": reason},
        )
    if reason in {"missing_recovery_context", "recovery_uncertain_side_effect"}:
        return ToolFailure(
            ToolFailureCategory.VERIFICATION,
            retryable=False,
            blame="recovery",
            recovery_hint=(
                "Inspect the durable receipt and external state before retrying."
            ),
            evidence={"tool_id": tool_id, "gate_reason": reason},
        )
    if reason in {"missing_idempotency_key", "recovery_idempotency_conflict"}:
        return ToolFailure(
            ToolFailureCategory.INVALID_ARGUMENTS,
            retryable=False,
            blame="recovery",
            recovery_hint=(
                "Provide a stable idempotency key that uniquely identifies "
                "this logical side effect."
            ),
            evidence={"tool_id": tool_id, "gate_reason": reason},
        )
    if reason == "recovery_retry_required":
        return ToolFailure(
            ToolFailureCategory.VERIFICATION,
            retryable=True,
            blame="recovery",
            recovery_hint=(
                "Explicitly authorize a retry after reviewing the failed receipt."
            ),
            evidence={"tool_id": tool_id, "gate_reason": reason},
        )
    if reason == "action_runtime_not_configured":
        return ToolFailure(
            ToolFailureCategory.ENVIRONMENT,
            retryable=False,
            blame="runtime",
            recovery_hint="Configure an ActionRuntime before requesting tool execution.",
            evidence={"tool_id": tool_id, "gate_reason": reason},
        )
    if reason == "action_loop_limit":
        return ToolFailure(
            ToolFailureCategory.VERIFICATION,
            retryable=False,
            blame="runtime",
            recovery_hint="Stop the loop and surface the unresolved goal to the caller.",
            evidence={"tool_id": tool_id, "gate_reason": reason},
        )
    return ToolFailure(
        ToolFailureCategory.EXECUTION,
        retryable=False,
        blame="runtime",
        recovery_hint="Inspect the action evidence before retrying.",
        evidence={"tool_id": tool_id, "gate_reason": reason},
    )


def failure_from_exception(exc: Exception, *, tool_id: str) -> ToolFailure:
    evidence = {
        "tool_id": tool_id,
        "exception_type": type(exc).__name__,
        "message": str(exc),
    }

    if isinstance(exc, TimeoutError):
        return ToolFailure(
            ToolFailureCategory.TIMEOUT,
            retryable=True,
            blame="environment",
            recovery_hint="Retry within the remaining attempt/time budget.",
            evidence=evidence,
        )
    if isinstance(exc, PermissionError):
        return ToolFailure(
            ToolFailureCategory.PERMISSION,
            retryable=False,
            blame="environment",
            recovery_hint="Change permissions or choose an allowed operation.",
            evidence=evidence,
        )
    if isinstance(exc, ConnectionError):
        return ToolFailure(
            ToolFailureCategory.TRANSIENT,
            retryable=True,
            blame="environment",
            recovery_hint="Retry after the external dependency becomes reachable.",
            evidence=evidence,
        )
    if isinstance(exc, (FileNotFoundError, NotADirectoryError, IsADirectoryError)):
        return ToolFailure(
            ToolFailureCategory.ENVIRONMENT,
            retryable=True,
            blame="environment",
            recovery_hint="Inspect the path/environment and retry with corrected context.",
            evidence=evidence,
        )
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return ToolFailure(
            ToolFailureCategory.INVALID_ARGUMENTS,
            retryable=True,
            blame="model",
            recovery_hint="Repair the tool arguments to match the declared schema.",
            evidence=evidence,
        )
    return ToolFailure(
        ToolFailureCategory.EXECUTION,
        retryable=False,
        blame="tool",
        recovery_hint="Inspect tool-specific evidence before deciding whether to retry.",
        evidence=evidence,
    )
