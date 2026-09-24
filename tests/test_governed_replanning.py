from __future__ import annotations

import pytest

from yisang.planning import (
    InMemoryPlanPort,
    PlanProposal,
    PlanRevisionProposal,
    PlanService,
    PlanStateError,
    PlanStepSpec,
)


def _service():
    service = PlanService(InMemoryPlanPort())
    service.accept_proposal(
        PlanProposal(
            proposal_id="initial",
            plan_id="plan-1",
            goal_id="goal-1",
            proposed_by="planner",
            steps=(
                PlanStepSpec("inspect", "Inspect"),
                PlanStepSpec(
                    "broken",
                    "Broken approach",
                    depends_on=("inspect",),
                    max_attempts=1,
                ),
                PlanStepSpec(
                    "verify-old",
                    "Verify old path",
                    depends_on=("broken",),
                ),
            ),
        ),
        actor="reviewer",
        reason="approved",
    )
    service.start_step("plan-1", "inspect", run_id="run-inspect")
    service.complete_step(
        "plan-1",
        "inspect",
        result_ref="result:inspect",
    )
    service.start_step("plan-1", "broken", run_id="run-broken")
    service.fail_step(
        "plan-1",
        "broken",
        error="approach failed",
    )
    return service


def _revision(service, *, base_revision=None):
    current = service.port.latest("plan-1")
    assert current is not None
    return PlanRevisionProposal(
        revision_proposal_id="revision-1",
        plan_id="plan-1",
        goal_id="goal-1",
        base_revision=(
            current.revision
            if base_revision is None
            else base_revision
        ),
        proposed_by="planner",
        reason="replace exhausted failed path",
        steps=(
            PlanStepSpec("inspect", "Inspect"),
            PlanStepSpec(
                "alternative",
                "Alternative approach",
                depends_on=("inspect",),
            ),
            PlanStepSpec(
                "verify-new",
                "Verify new path",
                depends_on=("alternative",),
            ),
        ),
    )


def test_replan_preserves_completed_step_and_replaces_future_work():
    service = _service()
    current = service.port.latest("plan-1")
    revised = service.accept_revision(
        _revision(service),
        actor="reviewer",
        reason="approved alternative",
    )

    inspect_before = next(
        step for step in current.steps if step.step_id == "inspect"
    )
    inspect_after = next(
        step for step in revised.steps if step.step_id == "inspect"
    )
    assert inspect_after.state == "completed"
    assert inspect_after.result_ref == inspect_before.result_ref
    assert {step.step_id for step in revised.steps} == {
        "inspect",
        "alternative",
        "verify-new",
    }
    assert service.execution_decision("plan-1").step_id == "alternative"


def test_replan_cannot_remove_completed_step():
    service = _service()
    current = service.port.latest("plan-1")
    proposal = PlanRevisionProposal(
        revision_proposal_id="bad-remove",
        plan_id="plan-1",
        goal_id="goal-1",
        base_revision=current.revision,
        proposed_by="planner",
        reason="bad",
        steps=(PlanStepSpec("alternative", "Alternative"),),
    )
    with pytest.raises(PlanStateError, match="completed step cannot be removed"):
        service.accept_revision(
            proposal,
            actor="reviewer",
            reason="should fail",
        )


def test_replan_cannot_change_existing_step_meaning():
    service = _service()
    current = service.port.latest("plan-1")
    proposal = PlanRevisionProposal(
        revision_proposal_id="bad-change",
        plan_id="plan-1",
        goal_id="goal-1",
        base_revision=current.revision,
        proposed_by="planner",
        reason="bad",
        steps=(
            PlanStepSpec("inspect", "Changed inspection semantics"),
            PlanStepSpec("alternative", "Alternative", depends_on=("inspect",)),
        ),
    )
    with pytest.raises(PlanStateError, match="completed step cannot be changed"):
        service.accept_revision(
            proposal,
            actor="reviewer",
            reason="should fail",
        )


def test_stale_revision_proposal_is_rejected():
    service = _service()
    current = service.port.latest("plan-1")
    with pytest.raises(PlanStateError, match="stale revision proposal"):
        service.accept_revision(
            _revision(service, base_revision=current.revision - 1),
            actor="reviewer",
            reason="stale",
        )


def test_running_step_must_be_resolved_before_replan():
    service = PlanService(InMemoryPlanPort())
    service.accept_proposal(
        PlanProposal(
            proposal_id="p",
            plan_id="running-plan",
            goal_id="g",
            proposed_by="planner",
            steps=(PlanStepSpec("a", "A"),),
        ),
        actor="reviewer",
        reason="approved",
    )
    running = service.start_step("running-plan", "a", run_id="run-a")
    proposal = PlanRevisionProposal(
        revision_proposal_id="rp",
        plan_id="running-plan",
        goal_id="g",
        base_revision=running.revision,
        proposed_by="planner",
        reason="change while running",
        steps=(PlanStepSpec("a", "A"),),
    )

    with pytest.raises(PlanStateError, match="running steps"):
        service.accept_revision(
            proposal,
            actor="reviewer",
            reason="should fail",
        )
