from __future__ import annotations

from .base import VerificationResult, Verifier


class ActionEvidenceVerifier(Verifier):
    """Fail closed when deterministic action evidence is denied or erroneous."""

    def __init__(self, *, require_actions: bool = False) -> None:
        self.require_actions = require_actions

    def verify(self, *, request, engine_result) -> VerificationResult:
        raw = engine_result.metadata.get("action_results", [])
        if not isinstance(raw, list):
            return VerificationResult("FAIL", "invalid_action_evidence")

        if not raw:
            if self.require_actions:
                return VerificationResult("FAIL", "missing_action_evidence")
            return VerificationResult("PASS", "no_actions")

        for item in raw:
            if not isinstance(item, dict):
                return VerificationResult("FAIL", "invalid_action_evidence")
            status = item.get("status")
            tool_id = item.get("tool_id", "unknown")
            if status == "DENIED":
                return VerificationResult("FAIL", f"action_denied:{tool_id}")
            if status == "ERROR":
                return VerificationResult("FAIL", f"action_error:{tool_id}")
            if status != "EXECUTED":
                return VerificationResult("FAIL", f"unknown_action_status:{tool_id}")

        return VerificationResult("PASS", "actions_verified")
