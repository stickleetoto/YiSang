from __future__ import annotations

from dataclasses import replace
import time

from .models import GOAL_STATES, GoalRecord
from .port import GoalPort


_ALLOWED_TRANSITIONS = {
    "planned": frozenset({"active", "cancelled"}),
    "active": frozenset({"blocked", "completed", "cancelled"}),
    "blocked": frozenset({"active", "cancelled"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
}


class GoalStateError(ValueError):
    pass


class GoalService:
    def __init__(self, port: GoalPort) -> None:
        self.port = port

    def transition(
        self,
        goal_id: str,
        state: str,
        *,
        blockers: tuple[str, ...] | None = None,
        next_action: str | None = None,
    ) -> GoalRecord:
        if state not in GOAL_STATES:
            raise GoalStateError(f"unsupported goal state: {state}")
        current = self._required(goal_id)
        if state == current.state:
            return current
        if state not in _ALLOWED_TRANSITIONS[current.state]:
            raise GoalStateError(
                f"invalid goal transition: {current.state} -> {state}"
            )
        updated = replace(
            current,
            state=state,
            blockers=(
                current.blockers if blockers is None else tuple(blockers)
            ),
            next_action=next_action,
            updated_at=time.time(),
        )
        self.port.update(updated)
        return updated

    def record_progress(
        self,
        goal_id: str,
        *,
        completed_work: str | None = None,
        next_action: str | None = None,
        blockers: tuple[str, ...] | None = None,
    ) -> GoalRecord:
        current = self._required(goal_id)
        if current.terminal:
            raise GoalStateError("terminal goals cannot record progress")
        completed = current.completed_work
        if completed_work is not None:
            value = completed_work.strip()
            if not value:
                raise ValueError("completed_work must be non-empty")
            completed = (*completed, value)
        updated = replace(
            current,
            completed_work=completed,
            next_action=next_action,
            blockers=(
                current.blockers if blockers is None else tuple(blockers)
            ),
            updated_at=time.time(),
        )
        self.port.update(updated)
        return updated

    def _required(self, goal_id: str) -> GoalRecord:
        goal = self.port.get(goal_id)
        if goal is None:
            raise KeyError(goal_id)
        return goal
