from __future__ import annotations

from yisang.execution.models import ActionResult

from .coordinator import RecoveryCoordinator
from .models import RecoveryCheckpoint


class VerifiedCheckpointOrchestrator:
    """Create one checkpoint per verified request, idempotently."""

    def __init__(self, recovery: RecoveryCoordinator) -> None:
        self.recovery = recovery

    def after_verification(
        self,
        *,
        goal_id: str,
        run_id: str,
        request_id: str,
        verification_status: str,
        action_results: list[ActionResult],
    ) -> RecoveryCheckpoint | None:
        if verification_status != "PASS":
            return None
        if any(item.status != "EXECUTED" for item in action_results):
            return None

        existing = self._existing_checkpoint(
            goal_id=goal_id,
            run_id=run_id,
            request_id=request_id,
        )
        if existing is not None:
            return existing

        completed_refs = tuple(
            dict.fromkeys(
                item.side_effect_receipt_id
                for item in action_results
                if item.side_effect_receipt_id is not None
            )
        )
        return self.recovery.write_checkpoint(
            goal_id=goal_id,
            run_id=run_id,
            completed_action_refs=completed_refs,
            metadata={
                "request_id": request_id,
                "verification_status": verification_status,
                "action_count": len(action_results),
            },
        )

    def _existing_checkpoint(
        self,
        *,
        goal_id: str,
        run_id: str,
        request_id: str,
    ) -> RecoveryCheckpoint | None:
        matches = [
            item
            for item in self.recovery.checkpoints.list_all(goal_id)
            if item.run_id == run_id
            and item.metadata.get("request_id") == request_id
            and item.metadata.get("verification_status") == "PASS"
        ]
        if not matches:
            return None
        return max(
            matches,
            key=lambda item: (
                item.created_at,
                item.journal_sequence,
                item.checkpoint_id,
            ),
        )
