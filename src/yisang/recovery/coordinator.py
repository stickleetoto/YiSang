from __future__ import annotations

import uuid

from yisang.goal import GoalPort

from .models import (
    RecoveryActionDecision,
    RecoveryCheckpoint,
    RecoveryPlan,
)
from .port import CheckpointPort, RunJournalPort, SideEffectReceiptPort


class RecoveryCoordinator:
    """Build checkpoints and conservative resume plans from durable state."""

    def __init__(
        self,
        *,
        goals: GoalPort,
        journal: RunJournalPort,
        checkpoints: CheckpointPort,
        side_effects: SideEffectReceiptPort | None = None,
    ) -> None:
        self.goals = goals
        self.journal = journal
        self.checkpoints = checkpoints
        self.side_effects = side_effects

    def write_checkpoint(
        self,
        *,
        goal_id: str,
        run_id: str,
        completed_action_refs: tuple[str, ...] = (),
        metadata: dict | None = None,
    ) -> RecoveryCheckpoint:
        goal = self.goals.get(goal_id)
        if goal is None:
            raise KeyError(goal_id)
        sequence = self.journal.latest_sequence(goal_id, run_id)
        checkpoint = RecoveryCheckpoint(
            checkpoint_id=f"checkpoint-{uuid.uuid4().hex[:16]}",
            goal_id=goal_id,
            run_id=run_id,
            journal_sequence=sequence,
            goal_state=goal.state,
            next_action=goal.next_action,
            completed_action_refs=tuple(completed_action_refs),
            blockers=goal.blockers,
            metadata=dict(metadata or {}),
        )
        self.checkpoints.put(checkpoint)
        self.journal.append(
            goal_id,
            run_id,
            "checkpoint_written",
            payload={
                "checkpoint_id": checkpoint.checkpoint_id,
                "covers_through_sequence": sequence,
            },
        )
        return checkpoint

    def plan_resume(
        self,
        goal_id: str,
        *,
        run_id: str | None = None,
    ) -> RecoveryPlan:
        goal = self.goals.get(goal_id)
        if goal is None:
            raise KeyError(goal_id)

        checkpoint = self.checkpoints.latest(goal_id, run_id=run_id)
        selected_run_id = (
            checkpoint.run_id if checkpoint is not None else run_id
        )
        journal_sequence = (
            checkpoint.journal_sequence if checkpoint is not None else 0
        )
        completed_refs = (
            checkpoint.completed_action_refs if checkpoint is not None else ()
        )
        blockers = (
            checkpoint.blockers if checkpoint is not None else goal.blockers
        )
        next_action = (
            checkpoint.next_action if checkpoint is not None else goal.next_action
        )

        if goal.state == "completed":
            return RecoveryPlan(
                goal_id=goal_id,
                run_id=selected_run_id,
                checkpoint_id=(
                    checkpoint.checkpoint_id if checkpoint is not None else None
                ),
                resume_allowed=False,
                reason="goal_completed",
                goal_state=goal.state,
                next_action=None,
                completed_action_refs=completed_refs,
                blockers=(),
                journal_sequence=journal_sequence,
            )
        if goal.state == "cancelled":
            return RecoveryPlan(
                goal_id=goal_id,
                run_id=selected_run_id,
                checkpoint_id=(
                    checkpoint.checkpoint_id if checkpoint is not None else None
                ),
                resume_allowed=False,
                reason="goal_cancelled",
                goal_state=goal.state,
                next_action=None,
                completed_action_refs=completed_refs,
                blockers=(),
                journal_sequence=journal_sequence,
            )
        if goal.state == "blocked":
            return RecoveryPlan(
                goal_id=goal_id,
                run_id=selected_run_id,
                checkpoint_id=(
                    checkpoint.checkpoint_id if checkpoint is not None else None
                ),
                resume_allowed=False,
                reason="goal_blocked",
                goal_state=goal.state,
                next_action=next_action,
                completed_action_refs=completed_refs,
                blockers=blockers,
                journal_sequence=journal_sequence,
            )

        return RecoveryPlan(
            goal_id=goal_id,
            run_id=selected_run_id,
            checkpoint_id=(
                checkpoint.checkpoint_id if checkpoint is not None else None
            ),
            resume_allowed=True,
            reason=(
                "checkpoint_available"
                if checkpoint is not None
                else "goal_state_available"
            ),
            goal_state=goal.state,
            next_action=next_action,
            completed_action_refs=completed_refs,
            blockers=blockers,
            journal_sequence=journal_sequence,
        )


    def reconcile_side_effect(
        self,
        *,
        goal_id: str,
        idempotency_key: str,
        request_digest: str,
    ) -> RecoveryActionDecision:
        if self.side_effects is None:
            return RecoveryActionDecision(
                goal_id=goal_id,
                idempotency_key=idempotency_key,
                decision="review",
                reason="side_effect_store_unavailable",
            )
        receipt = self.side_effects.get_receipt(
            goal_id,
            idempotency_key,
        )
        if receipt is None:
            return RecoveryActionDecision(
                goal_id=goal_id,
                idempotency_key=idempotency_key,
                decision="execute",
                reason="no_prior_receipt",
            )
        if receipt.request_digest != request_digest:
            return RecoveryActionDecision(
                goal_id=goal_id,
                idempotency_key=idempotency_key,
                decision="review",
                reason="idempotency_key_digest_conflict",
                receipt_id=receipt.receipt_id,
                receipt_state=receipt.state,
            )
        if receipt.state == "committed":
            return RecoveryActionDecision(
                goal_id=goal_id,
                idempotency_key=idempotency_key,
                decision="skip",
                reason="side_effect_already_committed",
                receipt_id=receipt.receipt_id,
                receipt_state=receipt.state,
            )
        if receipt.state == "started":
            return RecoveryActionDecision(
                goal_id=goal_id,
                idempotency_key=idempotency_key,
                decision="review",
                reason="side_effect_outcome_uncertain",
                receipt_id=receipt.receipt_id,
                receipt_state=receipt.state,
            )
        return RecoveryActionDecision(
            goal_id=goal_id,
            idempotency_key=idempotency_key,
            decision="retry",
            reason="previous_attempt_failed",
            receipt_id=receipt.receipt_id,
            receipt_state=receipt.state,
        )
