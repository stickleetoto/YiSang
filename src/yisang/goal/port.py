from __future__ import annotations

from abc import ABC, abstractmethod

from .models import GoalRecord


class GoalPort(ABC):
    """Authoritative durable goal state."""

    @abstractmethod
    def put(self, goal: GoalRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self, goal_id: str) -> GoalRecord | None:
        raise NotImplementedError

    @abstractmethod
    def update(self, goal: GoalRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_all(self) -> tuple[GoalRecord, ...]:
        raise NotImplementedError

    @abstractmethod
    def list_by_state(self, state: str) -> tuple[GoalRecord, ...]:
        raise NotImplementedError
