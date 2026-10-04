from __future__ import annotations

import pytest

from yisang.planning import (
    InMemoryPlanPort,
    LongHorizonScheduler,
    PlanCompileError,
    PlanCompiler,
    PlanProposal,
    PlanService,
    PlanStepSpec,
    SQLitePlanPort,
)


def _proposal():
    return PlanProposal(
        proposal_id="p1",
        plan_id="plan-1",
        goal_id="goal-1",
        proposed_by="planner",
        steps=(
            PlanStepSpec("a", "A", priority=1),
            PlanStepSpec("b", "B", depends_on=("a",), max_attempts=2),
        ),
    )


def test_compiler_rejects_cycle():
    proposal = PlanProposal(
        proposal_id="cycle",
        plan_id="plan-cycle",
        goal_id="goal-cycle",
        proposed_by="planner",
        steps=(
            PlanStepSpec("a", "A", depends_on=("b",)),
            PlanStepSpec("b", "B", depends_on=("a",)),
        ),
    )
    with pytest.raises(PlanCompileError, match="cycle"):
        PlanCompiler().compile(proposal)


def test_plan_progress_is_append_only_revisions():
    port = InMemoryPlanPort()
    service = PlanService(port)
    accepted = service.accept_proposal(
        _proposal(),
        actor="reviewer",
        reason="approved",
    )
    started = service.start_step("plan-1", "a")
    completed = service.complete_step(
        "plan-1",
        "a",
        result_ref="result:a",
    )

    assert accepted.revision == 1
    assert started.revision == 2
    assert completed.revision == 3
    assert [item.revision for item in port.history("plan-1")] == [1, 2, 3]
    assert port.history("plan-1")[0].steps[0].state == "pending"


def test_scheduler_selects_ready_dependency_order():
    service = PlanService(InMemoryPlanPort())
    service.accept_proposal(_proposal(), actor="reviewer", reason="approved")
    scheduler = LongHorizonScheduler(service)

    assert scheduler.decide("plan-1").step_id == "a"
    service.start_step("plan-1", "a")
    service.complete_step("plan-1", "a", result_ref="result:a")
    assert scheduler.decide("plan-1").step_id == "b"


def test_failed_step_can_retry_with_budget():
    service = PlanService(InMemoryPlanPort())
    service.accept_proposal(_proposal(), actor="reviewer", reason="approved")
    service.start_step("plan-1", "a")
    service.complete_step("plan-1", "a", result_ref="result:a")
    service.start_step("plan-1", "b")
    failed = service.fail_step("plan-1", "b", error="transient")

    assert failed.state == "blocked"
    decision = service.execution_decision("plan-1")
    assert decision.decision == "retry_step"
    retried = service.retry_step("plan-1", "b")
    step = next(item for item in retried.steps if item.step_id == "b")
    assert step.attempt_count == 2
    assert step.state == "running"


def test_sqlite_plan_history_survives_restart(tmp_path):
    db = tmp_path / "plans.db"
    with SQLitePlanPort(db) as port:
        service = PlanService(port)
        service.accept_proposal(_proposal(), actor="reviewer", reason="approved")
        service.start_step("plan-1", "a")

    with SQLitePlanPort(db) as port:
        latest = port.latest("plan-1")
        assert latest is not None
        assert latest.revision == 2
        assert [item.revision for item in port.history("plan-1")] == [1, 2]



def test_initial_compile_uses_proposal_timestamp():
    proposal = _proposal()
    compiled = PlanCompiler().compile(proposal)

    assert compiled.created_at == proposal.created_at
    assert compiled.updated_at == proposal.created_at
    assert compiled.revision == 1
