from __future__ import annotations

from dataclasses import replace
import time

from .compiler import PlanCompiler
from .models import (
    GoalPlan,
    PlanExecutionDecision,
    PlanProposal,
    PlanRevisionProposal,
    PlanStep,
)
from .port import PlanPort


class PlanStateError(ValueError):
    pass


class PlanService:
    def __init__(
        self,
        port: PlanPort,
        *,
        compiler: PlanCompiler | None = None,
    ) -> None:
        self.port = port
        self.compiler = compiler or PlanCompiler()

    def accept_proposal(
        self,
        proposal: PlanProposal,
        *,
        actor: str,
        reason: str,
        approval_ref: str | None = None,
    ) -> GoalPlan:
        if self.port.latest(proposal.plan_id) is not None:
            raise PlanStateError(
                f"plan already exists: {proposal.plan_id}"
            )
        actor = _required(actor, "actor")
        reason = _required(reason, "reason")
        plan = self.compiler.compile(
            proposal,
            provenance={
                "accepted_by": actor,
                "accept_reason": reason,
                "approval_ref": approval_ref,
            },
        )
        self.port.append(plan)
        return plan

    def accept_revision(
        self,
        proposal: PlanRevisionProposal,
        *,
        actor: str,
        reason: str,
        approval_ref: str | None = None,
    ) -> GoalPlan:
        current = self._required(proposal.plan_id)
        if proposal.base_revision != current.revision:
            raise PlanStateError(
                f"stale revision proposal: expected {current.revision}, "
                f"got {proposal.base_revision}"
            )
        actor = _required(actor, "actor")
        reason = _required(reason, "reason")
        try:
            revised = self.compiler.compile_revision(
                current,
                proposal,
                provenance={
                    "accepted_by": actor,
                    "accept_reason": reason,
                    "approval_ref": approval_ref,
                },
            )
        except ValueError as exc:
            raise PlanStateError(str(exc)) from exc
        self.port.append(revised)
        return revised

    def ready_steps(self, plan_id: str) -> tuple[PlanStep, ...]:
        plan = self._required(plan_id)
        if plan.state != "active":
            return ()
        completed = {
            step.step_id
            for step in plan.steps
            if step.state == "completed"
        }
        ready = [
            step
            for step in plan.steps
            if step.state == "pending"
            and set(step.depends_on).issubset(completed)
        ]
        return tuple(
            sorted(
                ready,
                key=lambda step: (
                    -step.priority,
                    step.ordinal,
                    step.step_id,
                ),
            )
        )

    def execution_decision(self, plan_id: str) -> PlanExecutionDecision:
        plan = self._required(plan_id)
        if plan.state == "completed":
            return PlanExecutionDecision(
                plan.plan_id,
                plan.revision,
                "completed",
                "all_steps_completed",
            )
        if plan.state in {"cancelled", "superseded"}:
            return PlanExecutionDecision(
                plan.plan_id,
                plan.revision,
                "stop",
                f"plan_{plan.state}",
            )

        running = tuple(
            step for step in plan.steps if step.state == "running"
        )
        if running:
            step = min(running, key=lambda item: item.ordinal)
            return PlanExecutionDecision(
                plan.plan_id,
                plan.revision,
                "wait",
                "step_running",
                step.step_id,
            )

        ready = self.ready_steps(plan_id)
        if ready:
            return PlanExecutionDecision(
                plan.plan_id,
                plan.revision,
                "start_step",
                "ready_step_available",
                ready[0].step_id,
            )

        retryable = tuple(
            step
            for step in plan.steps
            if step.state == "failed"
            and step.attempt_count < step.max_attempts
        )
        if retryable:
            step = min(
                retryable,
                key=lambda item: (
                    -item.priority,
                    item.ordinal,
                    item.step_id,
                ),
            )
            return PlanExecutionDecision(
                plan.plan_id,
                plan.revision,
                "retry_step",
                "retry_budget_available",
                step.step_id,
            )

        if any(step.state == "blocked" for step in plan.steps):
            return PlanExecutionDecision(
                plan.plan_id,
                plan.revision,
                "wait",
                "step_blocked",
            )

        if any(step.state == "failed" for step in plan.steps):
            return PlanExecutionDecision(
                plan.plan_id,
                plan.revision,
                "replan_required",
                "failed_step_exhausted",
            )

        return PlanExecutionDecision(
            plan.plan_id,
            plan.revision,
            "wait",
            "dependencies_not_ready",
        )

    def start_step(
        self,
        plan_id: str,
        step_id: str,
        *,
        run_id: str | None = None,
    ) -> GoalPlan:
        plan = self._required(plan_id)
        if plan.state not in {"active", "blocked"}:
            raise PlanStateError(
                f"plan cannot start a step from state {plan.state}"
            )
        step = self._step(plan, step_id)
        if step.state != "pending":
            raise PlanStateError(
                f"step cannot start from state {step.state}"
            )
        completed = {
            item.step_id
            for item in plan.steps
            if item.state == "completed"
        }
        if not set(step.depends_on).issubset(completed):
            raise PlanStateError("step dependencies are not completed")
        if step.attempt_count >= step.max_attempts:
            raise PlanStateError("step attempt budget exhausted")
        updated = replace(
            step,
            state="running",
            attempt_count=step.attempt_count + 1,
            blocker=None,
            last_error=None,
            run_id=_optional_text(run_id, "run_id"),
        )
        return self._replace_step(plan, updated, plan_state="active")

    def complete_step(
        self,
        plan_id: str,
        step_id: str,
        *,
        result_ref: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> GoalPlan:
        plan = self._required(plan_id)
        step = self._step(plan, step_id)
        if step.state != "running":
            raise PlanStateError(
                f"step cannot complete from state {step.state}"
            )
        result_ref = _required(result_ref, "result_ref")
        updated = replace(
            step,
            state="completed",
            result_ref=result_ref,
            evidence_refs=tuple(evidence_refs),
            blocker=None,
            last_error=None,
        )
        steps = tuple(
            updated if item.step_id == step_id else item
            for item in plan.steps
        )
        state = (
            "completed"
            if all(item.state == "completed" for item in steps)
            else "active"
        )
        return self._append_revision(plan, steps=steps, state=state)

    def fail_step(
        self,
        plan_id: str,
        step_id: str,
        *,
        error: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> GoalPlan:
        plan = self._required(plan_id)
        step = self._step(plan, step_id)
        if step.state != "running":
            raise PlanStateError(
                f"step cannot fail from state {step.state}"
            )
        error = _required(error, "error")
        updated = replace(
            step,
            state="failed",
            evidence_refs=tuple(evidence_refs),
            last_error=error,
        )
        return self._replace_step(plan, updated, plan_state="blocked")

    def retry_step(
        self,
        plan_id: str,
        step_id: str,
        *,
        run_id: str | None = None,
    ) -> GoalPlan:
        plan = self._required(plan_id)
        step = self._step(plan, step_id)
        if step.state != "failed":
            raise PlanStateError(
                f"step cannot retry from state {step.state}"
            )
        if step.attempt_count >= step.max_attempts:
            raise PlanStateError("step attempt budget exhausted")
        updated = replace(
            step,
            state="running",
            attempt_count=step.attempt_count + 1,
            last_error=None,
            blocker=None,
            run_id=_optional_text(run_id, "run_id"),
        )
        return self._replace_step(plan, updated, plan_state="active")

    def block_step(
        self,
        plan_id: str,
        step_id: str,
        *,
        blocker: str,
    ) -> GoalPlan:
        plan = self._required(plan_id)
        step = self._step(plan, step_id)
        if step.state not in {"pending", "running"}:
            raise PlanStateError(
                f"step cannot block from state {step.state}"
            )
        blocker = _required(blocker, "blocker")
        updated = replace(
            step,
            state="blocked",
            blocker=blocker,
        )
        return self._replace_step(plan, updated, plan_state="blocked")

    def unblock_step(self, plan_id: str, step_id: str) -> GoalPlan:
        plan = self._required(plan_id)
        step = self._step(plan, step_id)
        if step.state != "blocked":
            raise PlanStateError("only blocked steps may be unblocked")
        updated = replace(
            step,
            state="pending",
            blocker=None,
        )
        return self._replace_step(plan, updated, plan_state="active")

    def cancel(self, plan_id: str, *, reason: str) -> GoalPlan:
        plan = self._required(plan_id)
        if plan.terminal:
            raise PlanStateError("terminal plan cannot be cancelled")
        reason = _required(reason, "reason")
        provenance = dict(plan.provenance)
        provenance["cancel_reason"] = reason
        return self._append_revision(
            plan,
            steps=plan.steps,
            state="cancelled",
            provenance=provenance,
        )

    def _replace_step(
        self,
        plan: GoalPlan,
        updated: PlanStep,
        *,
        plan_state: str,
    ) -> GoalPlan:
        steps = tuple(
            updated if item.step_id == updated.step_id else item
            for item in plan.steps
        )
        return self._append_revision(
            plan,
            steps=steps,
            state=plan_state,
        )

    def _append_revision(
        self,
        plan: GoalPlan,
        *,
        steps: tuple[PlanStep, ...],
        state: str,
        provenance: dict | None = None,
    ) -> GoalPlan:
        updated = GoalPlan(
            plan_id=plan.plan_id,
            goal_id=plan.goal_id,
            revision=plan.revision + 1,
            state=state,
            steps=steps,
            provenance=(
                dict(plan.provenance)
                if provenance is None
                else dict(provenance)
            ),
            created_at=plan.created_at,
            updated_at=time.time(),
        )
        self.port.append(updated)
        return updated

    def _required(self, plan_id: str) -> GoalPlan:
        plan = self.port.latest(plan_id)
        if plan is None:
            raise KeyError(plan_id)
        return plan

    @staticmethod
    def _step(plan: GoalPlan, step_id: str) -> PlanStep:
        for step in plan.steps:
            if step.step_id == step_id:
                return step
        raise KeyError(step_id)


def _required(value: str, name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{name} must be non-empty")
    return normalized



def _optional_text(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{name} must be non-empty when provided")
    return normalized
