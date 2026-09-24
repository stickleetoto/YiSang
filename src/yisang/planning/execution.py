from __future__ import annotations

from yisang.goal import GoalService
from yisang.recovery import CrashRecoveryPlanner, RecoveryRunController

from .models import (
    LongHorizonResumeDecision,
    PlanStep,
    PlanStepRun,
)
from .service import PlanService, PlanStateError


class LongHorizonExecutionCoordinator:
    """Bridge durable plan steps onto v0.8 durable goal runs."""

    def __init__(
        self,
        *,
        plans: PlanService,
        goals: GoalService,
        recovery: RecoveryRunController,
        crash_planner: CrashRecoveryPlanner,
    ) -> None:
        self.plans = plans
        self.goals = goals
        self.recovery = recovery
        self.crash_planner = crash_planner

    def start_next(
        self,
        plan_id: str,
        *,
        run_id: str,
    ) -> PlanStepRun:
        decision = self.plans.execution_decision(plan_id)
        plan = self._plan(plan_id)

        if decision.decision == "wait" and decision.reason == "step_running":
            step = self._step(plan, decision.step_id)
            if step.run_id != run_id:
                raise PlanStateError(
                    "plan already has a running step on a different run_id"
                )
            return self._binding(plan, step)

        if decision.decision not in {"start_step", "retry_step"}:
            raise PlanStateError(
                f"plan cannot start next step: "
                f"{decision.decision}/{decision.reason}"
            )

        step = self._step(plan, decision.step_id)
        goal = self.goals.port.get(plan.goal_id)
        if goal is None:
            raise KeyError(plan.goal_id)
        if goal.state == "blocked":
            self.recovery.unblock(
                plan.goal_id,
                next_action=_step_action(step),
            )
        self.recovery.start(plan.goal_id, run_id)
        self.goals.record_progress(
            plan.goal_id,
            next_action=_step_action(step),
            blockers=(),
        )

        if decision.decision == "start_step":
            updated = self.plans.start_step(
                plan_id,
                step.step_id,
                run_id=run_id,
            )
        else:
            updated = self.plans.retry_step(
                plan_id,
                step.step_id,
                run_id=run_id,
            )
        running = self._step(updated, step.step_id)
        self.recovery.journal.append(
            plan.goal_id,
            run_id,
            "step_planned",
            payload={
                "plan_id": plan_id,
                "plan_revision": updated.revision,
                "step_id": running.step_id,
                "attempt_count": running.attempt_count,
            },
        )
        return self._binding(updated, running)

    def complete_step(
        self,
        plan_id: str,
        step_id: str,
        *,
        run_id: str,
        result_ref: str,
        evidence_refs: tuple[str, ...] = (),
    ):
        plan = self._plan(plan_id)
        step = self._step(plan, step_id)
        self._require_run(step, run_id)
        updated = self.plans.complete_step(
            plan_id,
            step_id,
            result_ref=result_ref,
            evidence_refs=evidence_refs,
        )
        self.recovery.journal.append(
            plan.goal_id,
            run_id,
            "step_completed",
            payload={
                "plan_id": plan_id,
                "plan_revision": updated.revision,
                "step_id": step_id,
                "result_ref": result_ref,
                "evidence_refs": list(evidence_refs),
            },
        )

        if updated.state == "completed":
            self.recovery.journal.append(
                plan.goal_id,
                run_id,
                "plan_completed",
                payload={
                    "plan_id": plan_id,
                    "plan_revision": updated.revision,
                },
            )
            self.recovery.complete(
                plan.goal_id,
                run_id,
                completed_work=step.title,
            )
            return updated

        next_action = _decision_next_action(
            self.plans,
            updated.plan_id,
        )
        self.goals.record_progress(
            plan.goal_id,
            completed_work=step.title,
            next_action=next_action,
            blockers=(),
        )
        self.recovery.checkpoint(
            plan.goal_id,
            run_id,
            metadata={
                "plan_id": plan_id,
                "plan_revision": updated.revision,
                "completed_step_id": step_id,
            },
        )
        return updated

    def fail_step(
        self,
        plan_id: str,
        step_id: str,
        *,
        run_id: str,
        error: str,
        evidence_refs: tuple[str, ...] = (),
    ):
        plan = self._plan(plan_id)
        step = self._step(plan, step_id)
        self._require_run(step, run_id)
        updated = self.plans.fail_step(
            plan_id,
            step_id,
            error=error,
            evidence_refs=evidence_refs,
        )
        self.recovery.journal.append(
            plan.goal_id,
            run_id,
            "step_failed",
            payload={
                "plan_id": plan_id,
                "plan_revision": updated.revision,
                "step_id": step_id,
                "error": error,
                "evidence_refs": list(evidence_refs),
            },
        )
        decision = self.plans.execution_decision(plan_id)
        next_action = (
            f"retry plan step {step_id}"
            if decision.decision == "retry_step"
            else f"replan after failed step {step_id}"
        )
        self.recovery.block(
            plan.goal_id,
            run_id,
            blocker=error,
            next_action=next_action,
        )
        return updated

    def assess_resume(self, plan_id: str) -> LongHorizonResumeDecision:
        plan = self._plan(plan_id)
        running = tuple(
            step for step in plan.steps if step.state == "running"
        )
        if running:
            step = min(running, key=lambda item: item.ordinal)
            if step.run_id is None:
                return LongHorizonResumeDecision(
                    plan_id=plan.plan_id,
                    plan_revision=plan.revision,
                    decision="replan_required",
                    reason="running_step_missing_run_id",
                    step_id=step.step_id,
                )
            directive = self.crash_planner.plan(
                plan.goal_id,
                run_id=step.run_id,
            )
            return LongHorizonResumeDecision(
                plan_id=plan.plan_id,
                plan_revision=plan.revision,
                decision="recover_running_step",
                reason="running_step_has_durable_run",
                step_id=step.step_id,
                run_id=step.run_id,
                recovery_mode=directive.mode,
                recovery_reason=directive.reason,
            )

        decision = self.plans.execution_decision(plan_id)
        return LongHorizonResumeDecision(
            plan_id=plan.plan_id,
            plan_revision=plan.revision,
            decision=decision.decision,
            reason=decision.reason,
            step_id=decision.step_id,
        )

    def _plan(self, plan_id: str):
        plan = self.plans.port.latest(plan_id)
        if plan is None:
            raise KeyError(plan_id)
        return plan

    @staticmethod
    def _step(plan, step_id: str | None) -> PlanStep:
        if step_id is None:
            raise PlanStateError("step_id is required")
        for step in plan.steps:
            if step.step_id == step_id:
                return step
        raise KeyError(step_id)

    @staticmethod
    def _require_run(step: PlanStep, run_id: str) -> None:
        if step.run_id != run_id:
            raise PlanStateError(
                f"step {step.step_id} is bound to run {step.run_id!r}, "
                f"not {run_id!r}"
            )

    @staticmethod
    def _binding(plan, step: PlanStep) -> PlanStepRun:
        assert step.run_id is not None
        return PlanStepRun(
            plan_id=plan.plan_id,
            plan_revision=plan.revision,
            goal_id=plan.goal_id,
            step_id=step.step_id,
            run_id=step.run_id,
            title=step.title,
            attempt_count=step.attempt_count,
        )


def _step_action(step: PlanStep) -> str:
    return step.description.strip() or step.title


def _decision_next_action(
    plans: PlanService,
    plan_id: str,
) -> str | None:
    decision = plans.execution_decision(plan_id)
    if decision.step_id is None:
        return None
    plan = plans.port.latest(plan_id)
    if plan is None:
        return None
    for step in plan.steps:
        if step.step_id == decision.step_id:
            return _step_action(step)
    return None
