from __future__ import annotations

from dataclasses import dataclass
from typing import Any


RECOVERY_FAULT_POINTS = frozenset(
    {
        "after_side_effect_reserved",
        "after_handler_success_before_receipt_commit",
        "after_side_effect_committed",
    }
)


class InjectedRecoveryCrash(BaseException):
    """Hard-crash test signal intentionally not caught by Exception handlers."""

    def __init__(self, point: str) -> None:
        self.point = point
        super().__init__(f"injected recovery crash at {point}")


class RecoveryFaultInjector:
    def hit(self, point: str, context: dict[str, Any]) -> None:
        if point not in RECOVERY_FAULT_POINTS:
            raise ValueError(f"unsupported recovery fault point: {point}")


@dataclass
class DeterministicRecoveryFaultInjector(RecoveryFaultInjector):
    point: str
    remaining: int = 1

    def __post_init__(self) -> None:
        if self.point not in RECOVERY_FAULT_POINTS:
            raise ValueError(f"unsupported recovery fault point: {self.point}")
        if self.remaining <= 0:
            raise ValueError("remaining must be positive")

    def hit(self, point: str, context: dict[str, Any]) -> None:
        super().hit(point, context)
        if point != self.point or self.remaining <= 0:
            return
        self.remaining -= 1
        raise InjectedRecoveryCrash(point)
