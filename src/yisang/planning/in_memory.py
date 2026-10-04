from __future__ import annotations

from .models import GoalPlan
from .port import PlanPort


class InMemoryPlanPort(PlanPort):
    def __init__(self) -> None:
        self._plans: dict[str, list[GoalPlan]] = {}

    def append(self, plan: GoalPlan) -> None:
        history = self._plans.setdefault(plan.plan_id, [])
        if not history:
            if plan.revision != 1:
                raise ValueError("first plan revision must be 1")
        else:
            previous = history[-1]
            if plan.goal_id != previous.goal_id:
                raise ValueError("plan goal_id is immutable")
            if plan.created_at != previous.created_at:
                raise ValueError("plan created_at is immutable")
            if plan.revision != previous.revision + 1:
                raise ValueError(
                    "plan revisions must be sequential"
                )
        history.append(plan)

    def latest(self, plan_id: str) -> GoalPlan | None:
        history = self._plans.get(plan_id)
        return None if not history else history[-1]

    def history(self, plan_id: str) -> tuple[GoalPlan, ...]:
        return tuple(self._plans.get(plan_id, ()))

    def latest_for_goal(self, goal_id: str) -> GoalPlan | None:
        candidates = [
            items[-1]
            for items in self._plans.values()
            if items and items[-1].goal_id == goal_id
        ]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda item: (item.updated_at, item.plan_id),
        )
