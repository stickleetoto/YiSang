from __future__ import annotations

from yisang.goal import GoalService, GoalStateError

from .coordinator import RecoveryCoordinator
from .models import RecoveryCheckpoint, RestartAssessment
from .port import RunJournalPort


class RecoveryRunController:
    """Explicit lifecycle controller for a durable goal run."""

    def __init__(
        self,
        *,
        goals: GoalService,
        recovery: RecoveryCoordinator,
        journal: RunJournalPort,
    ) -> None:
        self.goals = goals
        self.recovery = recovery
        self.journal = journal

    def start(self, goal_id: str, run_id: str):
        goal = self.goals.port.get(goal_id)
        if goal is None:
            raise KeyError(goal_id)
        if goal.state == "planned":
            goal = self.goals.transition(
                goal_id,
                "active",
                next_action=goal.next_action,
            )
        elif goal.state != "active":
            raise GoalStateError(
                f"goal cannot start from state {goal.state}"
            )
        if self.journal.latest_sequence(goal_id, run_id) == 0:
            self.journal.append(
                goal_id,
                run_id,
                "goal_started",
                payload={"goal_state": goal.state},
            )
        return goal

    def checkpoint(
        self,
        goal_id: str,
        run_id: str,
        *,
        completed_action_refs: tuple[str, ...] = (),
        metadata: dict | None = None,
    ) -> RecoveryCheckpoint:
        return self.recovery.write_checkpoint(
            goal_id=goal_id,
            run_id=run_id,
            completed_action_refs=completed_action_refs,
            metadata=metadata,
        )

    def block(
        self,
        goal_id: str,
        run_id: str,
        *,
        blocker: str,
        next_action: str | None = None,
    ) -> RecoveryCheckpoint:
        value = blocker.strip()
        if not value:
            raise ValueError("blocker must be non-empty")
        goal = self.goals.record_progress(
            goal_id,
            blockers=(value,),
            next_action=next_action,
        )
        if goal.state == "active":
            goal = self.goals.transition(
                goal_id,
                "blocked",
                blockers=(value,),
                next_action=next_action,
            )
        elif goal.state != "blocked":
            raise GoalStateError(
                f"goal cannot be blocked from state {goal.state}"
            )
        self.journal.append(
            goal_id,
            run_id,
            "blocker_detected",
            payload={
                "blocker": value,
                "next_action": next_action,
            },
        )
        return self.checkpoint(goal_id, run_id)

    def unblock(
        self,
        goal_id: str,
        *,
        next_action: str | None = None,
    ):
        goal = self.goals.port.get(goal_id)
        if goal is None:
            raise KeyError(goal_id)
        if goal.state != "blocked":
            raise GoalStateError("only blocked goals may be unblocked")
        return self.goals.transition(
            goal_id,
            "active",
            blockers=(),
            next_action=next_action,
        )

    def complete(
        self,
        goal_id: str,
        run_id: str,
        *,
        completed_work: str | None = None,
        completed_action_refs: tuple[str, ...] = (),
    ) -> RecoveryCheckpoint:
        goal = self.goals.port.get(goal_id)
        if goal is None:
            raise KeyError(goal_id)
        if completed_work is not None:
            goal = self.goals.record_progress(
                goal_id,
                completed_work=completed_work,
                next_action=None,
            )
        if goal.state != "active":
            raise GoalStateError(
                f"goal cannot complete from state {goal.state}"
            )
        self.goals.transition(
            goal_id,
            "completed",
            blockers=(),
            next_action=None,
        )
        self.journal.append(
            goal_id,
            run_id,
            "goal_completed",
            payload={"completed_work": completed_work},
        )
        return self.checkpoint(
            goal_id,
            run_id,
            completed_action_refs=completed_action_refs,
        )

    def cancel(
        self,
        goal_id: str,
        run_id: str,
        *,
        reason: str,
    ) -> RecoveryCheckpoint:
        value = reason.strip()
        if not value:
            raise ValueError("reason must be non-empty")
        goal = self.goals.port.get(goal_id)
        if goal is None:
            raise KeyError(goal_id)
        if goal.terminal:
            raise GoalStateError("terminal goal cannot be cancelled")
        self.goals.transition(
            goal_id,
            "cancelled",
            blockers=(),
            next_action=None,
        )
        self.journal.append(
            goal_id,
            run_id,
            "goal_cancelled",
            payload={"reason": value},
        )
        return self.checkpoint(goal_id, run_id)

    def assess_restart(
        self,
        goal_id: str,
        *,
        run_id: str | None = None,
    ) -> RestartAssessment:
        return self.recovery.assess_restart(goal_id, run_id=run_id)
