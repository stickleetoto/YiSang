from __future__ import annotations

from yisang.goal import GoalRecord, GoalService, InMemoryGoalPort
from yisang.planning import (
    InMemoryPlanPort,
    LongHorizonExecutionCoordinator,
    PlanProposal,
    PlanService,
    PlanStepSpec,
)
from yisang.recovery import (
    CrashRecoveryPlanner,
    InMemoryCheckpointPort,
    InMemoryRunJournalPort,
    InMemorySideEffectReceiptPort,
    RecoveryCoordinator,
    RecoveryRunController,
)


def _stack():
    goal_port = InMemoryGoalPort()
    goal_port.put(
        GoalRecord(
            goal_id="goal-1",
            description="complete a two-step job",
            state="planned",
        )
    )
    goals = GoalService(goal_port)
    plan_service = PlanService(InMemoryPlanPort())
    plan_service.accept_proposal(
        PlanProposal(
            proposal_id="proposal-1",
            plan_id="plan-1",
            goal_id="goal-1",
            proposed_by="planner",
            steps=(
                PlanStepSpec("a", "Inspect"),
                PlanStepSpec("b", "Edit", depends_on=("a",), max_attempts=2),
            ),
        ),
        actor="reviewer",
        reason="approved",
    )
    journal = InMemoryRunJournalPort()
    recovery_coord = RecoveryCoordinator(
        goals=goal_port,
        journal=journal,
        checkpoints=InMemoryCheckpointPort(),
        side_effects=InMemorySideEffectReceiptPort(),
    )
    recovery = RecoveryRunController(
        goals=goals,
        recovery=recovery_coord,
        journal=journal,
    )
    coordinator = LongHorizonExecutionCoordinator(
        plans=plan_service,
        goals=goals,
        recovery=recovery,
        crash_planner=CrashRecoveryPlanner(recovery_coord),
    )
    return goal_port, plan_service, journal, coordinator


def test_start_next_binds_plan_step_to_recovery_run():
    goals, plans, journal, coordinator = _stack()

    binding = coordinator.start_next("plan-1", run_id="run-a")
    latest = plans.port.latest("plan-1")
    step = next(item for item in latest.steps if item.step_id == "a")

    assert binding.step_id == "a"
    assert binding.run_id == "run-a"
    assert step.run_id == "run-a"
    assert step.state == "running"
    assert goals.get("goal-1").state == "active"
    assert any(
        item.event_type == "step_planned"
        for item in journal.events("goal-1", run_id="run-a")
    )


def test_completed_step_advances_goal_next_action_and_checkpoints():
    goals, plans, journal, coordinator = _stack()
    coordinator.start_next("plan-1", run_id="run-a")

    updated = coordinator.complete_step(
        "plan-1",
        "a",
        run_id="run-a",
        result_ref="result:a",
    )

    assert updated.state == "active"
    assert goals.get("goal-1").next_action == "Edit"
    assert plans.execution_decision("plan-1").step_id == "b"
    assert any(
        item.event_type == "checkpoint_written"
        for item in journal.events("goal-1", run_id="run-a")
    )


def test_failure_blocks_goal_and_retry_uses_new_run():
    goals, plans, _journal, coordinator = _stack()
    coordinator.start_next("plan-1", run_id="run-a")
    coordinator.complete_step(
        "plan-1",
        "a",
        run_id="run-a",
        result_ref="result:a",
    )
    coordinator.start_next("plan-1", run_id="run-b1")
    coordinator.fail_step(
        "plan-1",
        "b",
        run_id="run-b1",
        error="transient",
    )

    assert goals.get("goal-1").state == "blocked"
    assert plans.execution_decision("plan-1").decision == "retry_step"

    binding = coordinator.start_next("plan-1", run_id="run-b2")
    assert binding.step_id == "b"
    assert binding.run_id == "run-b2"
    assert binding.attempt_count == 2
    assert goals.get("goal-1").state == "active"


def test_assess_resume_uses_bound_recovery_run():
    _goals, _plans, _journal, coordinator = _stack()
    coordinator.start_next("plan-1", run_id="run-a")

    decision = coordinator.assess_resume("plan-1")

    assert decision.decision == "recover_running_step"
    assert decision.step_id == "a"
    assert decision.run_id == "run-a"
    assert decision.recovery_mode is not None
