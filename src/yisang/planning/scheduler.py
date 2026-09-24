from __future__ import annotations

from .models import PlanExecutionDecision
from .service import PlanService


class LongHorizonScheduler:
    """Deterministic scheduler over durable plan state."""

    def __init__(self, plans: PlanService) -> None:
        self.plans = plans

    def decide(self, plan_id: str) -> PlanExecutionDecision:
        return self.plans.execution_decision(plan_id)
