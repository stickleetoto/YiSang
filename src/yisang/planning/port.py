from __future__ import annotations

from abc import ABC, abstractmethod

from .models import GoalPlan


class PlanPort(ABC):
    """Append-only authoritative plan revision store."""

    @abstractmethod
    def append(self, plan: GoalPlan) -> None:
        raise NotImplementedError

    @abstractmethod
    def latest(self, plan_id: str) -> GoalPlan | None:
        raise NotImplementedError

    @abstractmethod
    def history(self, plan_id: str) -> tuple[GoalPlan, ...]:
        raise NotImplementedError

    @abstractmethod
    def latest_for_goal(self, goal_id: str) -> GoalPlan | None:
        raise NotImplementedError
