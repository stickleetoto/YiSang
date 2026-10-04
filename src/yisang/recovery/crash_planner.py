from __future__ import annotations

from .coordinator import RecoveryCoordinator
from .models import CrashRecoveryDirective


class CrashRecoveryPlanner:
    """Classify the safest next recovery operation without executing it."""

    def __init__(self, recovery: RecoveryCoordinator) -> None:
        self.recovery = recovery

    def plan(
        self,
        goal_id: str,
        *,
        run_id: str | None = None,
    ) -> CrashRecoveryDirective:
        assessment = self.recovery.assess_restart(
            goal_id,
            run_id=run_id,
        )
        plan = assessment.plan

        if assessment.uncertain_receipt_ids:
            return CrashRecoveryDirective(
                goal_id=goal_id,
                run_id=plan.run_id,
                mode="reconcile_side_effect",
                reason="uncertain_side_effects",
                checkpoint_id=plan.checkpoint_id,
                post_checkpoint_event_ids=assessment.post_checkpoint_event_ids,
                uncertain_receipt_ids=assessment.uncertain_receipt_ids,
                retryable_receipt_ids=assessment.retryable_receipt_ids,
            )

        if not plan.resume_allowed:
            return CrashRecoveryDirective(
                goal_id=goal_id,
                run_id=plan.run_id,
                mode="stop",
                reason=assessment.reason,
                checkpoint_id=plan.checkpoint_id,
                post_checkpoint_event_ids=assessment.post_checkpoint_event_ids,
                retryable_receipt_ids=assessment.retryable_receipt_ids,
            )

        events = ()
        if plan.run_id is not None:
            events = self.recovery.journal.events(
                goal_id,
                run_id=plan.run_id,
                after_sequence=plan.journal_sequence,
            )

        if not events:
            return CrashRecoveryDirective(
                goal_id=goal_id,
                run_id=plan.run_id,
                mode="resume_next_action",
                reason="checkpoint_is_current",
                checkpoint_id=plan.checkpoint_id,
                retryable_receipt_ids=assessment.retryable_receipt_ids,
            )

        last = events[-1]
        if last.event_type == "verification_result":
            if last.payload.get("status") == "PASS":
                return CrashRecoveryDirective(
                    goal_id=goal_id,
                    run_id=plan.run_id,
                    mode="write_checkpoint",
                    reason="verified_work_not_checkpointed",
                    checkpoint_id=plan.checkpoint_id,
                    post_checkpoint_event_ids=tuple(
                        item.event_id for item in events
                    ),
                    retryable_receipt_ids=assessment.retryable_receipt_ids,
                )
            return CrashRecoveryDirective(
                goal_id=goal_id,
                run_id=plan.run_id,
                mode="resume_next_action",
                reason="prior_verification_failed",
                checkpoint_id=plan.checkpoint_id,
                post_checkpoint_event_ids=tuple(
                    item.event_id for item in events
                ),
                retryable_receipt_ids=assessment.retryable_receipt_ids,
            )

        if last.event_type in {
            "action_executed",
            "side_effect_committed",
        }:
            return CrashRecoveryDirective(
                goal_id=goal_id,
                run_id=plan.run_id,
                mode="verify_prior_action",
                reason="executed_work_not_verified",
                checkpoint_id=plan.checkpoint_id,
                post_checkpoint_event_ids=tuple(
                    item.event_id for item in events
                ),
                retryable_receipt_ids=assessment.retryable_receipt_ids,
            )

        if last.event_type == "checkpoint_written":
            return CrashRecoveryDirective(
                goal_id=goal_id,
                run_id=plan.run_id,
                mode="resume_next_action",
                reason="checkpoint_is_current",
                checkpoint_id=plan.checkpoint_id,
                post_checkpoint_event_ids=tuple(
                    item.event_id for item in events
                ),
                retryable_receipt_ids=assessment.retryable_receipt_ids,
            )

        return CrashRecoveryDirective(
            goal_id=goal_id,
            run_id=plan.run_id,
            mode="resume_next_action",
            reason=f"resume_after_{last.event_type}",
            checkpoint_id=plan.checkpoint_id,
            post_checkpoint_event_ids=tuple(
                item.event_id for item in events
            ),
            retryable_receipt_ids=assessment.retryable_receipt_ids,
        )
