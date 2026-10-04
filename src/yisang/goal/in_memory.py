from __future__ import annotations

from .models import GOAL_STATES, GoalRecord
from .port import GoalPort


class InMemoryGoalPort(GoalPort):
    def __init__(self) -> None:
        self._goals: dict[str, GoalRecord] = {}

    def put(self, goal: GoalRecord) -> None:
        if goal.goal_id in self._goals:
            raise ValueError(f"duplicate goal: {goal.goal_id}")
        self._goals[goal.goal_id] = goal

    def get(self, goal_id: str) -> GoalRecord | None:
        return self._goals.get(goal_id)

    def update(self, goal: GoalRecord) -> None:
        current = self._goals.get(goal.goal_id)
        if current is None:
            raise KeyError(goal.goal_id)
        if goal.created_at != current.created_at:
            raise ValueError("goal created_at is immutable")
        self._goals[goal.goal_id] = goal

    def list_all(self) -> tuple[GoalRecord, ...]:
        return tuple(
            sorted(self._goals.values(), key=lambda item: item.goal_id)
        )

    def list_by_state(self, state: str) -> tuple[GoalRecord, ...]:
        if state not in GOAL_STATES:
            raise ValueError(f"unsupported goal state: {state}")
        return tuple(
            item for item in self.list_all() if item.state == state
        )
