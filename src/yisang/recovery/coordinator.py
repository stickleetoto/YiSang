from __future__ import annotations

import uuid

from yisang.goal import GoalPort

from .models import RecoveryCheckpoint, RecoveryPlan
from .port import CheckpointPort, RunJournalPort


class RecoveryCoordinator:
    """Build checkpoints and conservative resume plans from durable state."""

    def __init__(
        self,
        *,
        goals: GoalPort,
        journal: RunJournalPort,
        checkpoints: CheckpointPort,
    ) -> None:
        self.goals = goals
        self.journal = journal
        self.checkpoints = checkpoints

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
