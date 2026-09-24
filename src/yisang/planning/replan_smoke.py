from __future__ import annotations

import argparse
import json

from yisang.goal import GoalRecord, GoalService, InMemoryGoalPort
from yisang.planning import (
    InMemoryPlanPort,
    LongHorizonExecutionCoordinator,
    PlanProposal,
    PlanRevisionProposal,
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yisang-replan-smoke")
    parser.parse_args(argv)

    goal_port = InMemoryGoalPort()
    goal_port.put(
        GoalRecord(
            goal_id="goal-replan",
            description="finish despite one exhausted approach",
            state="planned",
        )
    )
    goals = GoalService(goal_port)
    plans = PlanService(InMemoryPlanPort())
    plans.accept_proposal(
        PlanProposal(
            proposal_id="initial",
            plan_id="plan-replan",
            goal_id="goal-replan",
            proposed_by="planner",
            steps=(
                PlanStepSpec("inspect", "Inspect"),
                PlanStepSpec(
                    "broken",
                    "Broken approach",
                    depends_on=("inspect",),
                    max_attempts=1,
                ),
            ),
        ),
        actor="reviewer",
        reason="approved initial plan",
    )

    journal = InMemoryRunJournalPort()
    recovery_coord = RecoveryCoordinator(
        goals=goal_port,
        journal=journal,
        checkpoints=InMemoryCheckpointPort(),
        side_effects=InMemorySideEffectReceiptPort(),
    )
    bridge = LongHorizonExecutionCoordinator(
        plans=plans,
        goals=goals,
        recovery=RecoveryRunController(
            goals=goals,
            recovery=recovery_coord,
            journal=journal,
        ),
        crash_planner=CrashRecoveryPlanner(recovery_coord),
    )

    bridge.start_next("plan-replan", run_id="run-inspect")
    bridge.complete_step(
        "plan-replan",
        "inspect",
        run_id="run-inspect",
        result_ref="result:inspect",
    )
    bridge.start_next("plan-replan", run_id="run-broken")
    bridge.fail_step(
        "plan-replan",
        "broken",
        run_id="run-broken",
        error="exhausted approach",
    )
    before = plans.execution_decision("plan-replan")
    current = plans.port.latest("plan-replan")
    assert current is not None

    revised = plans.accept_revision(
        PlanRevisionProposal(
            revision_proposal_id="replan-1",
            plan_id="plan-replan",
            goal_id="goal-replan",
            base_revision=current.revision,
            proposed_by="planner",
            reason="replace exhausted approach",
            steps=(
                PlanStepSpec("inspect", "Inspect"),
                PlanStepSpec(
                    "alternative",
                    "Alternative",
                    depends_on=("inspect",),
                ),
                PlanStepSpec(
                    "verify",
                    "Verify",
                    depends_on=("alternative",),
                ),
            ),
        ),
        actor="reviewer",
        reason="approved replan",
    )

    alternative = bridge.start_next(
        "plan-replan",
        run_id="run-alternative",
    )
    bridge.complete_step(
        "plan-replan",
        "alternative",
        run_id="run-alternative",
        result_ref="result:alternative",
    )
    verify = bridge.start_next(
        "plan-replan",
        run_id="run-verify",
    )
    final = bridge.complete_step(
        "plan-replan",
        "verify",
        run_id="run-verify",
        result_ref="result:verify",
    )
    goal = goal_port.get("goal-replan")
    inspect = next(
        step for step in final.steps if step.step_id == "inspect"
    )

    payload = {
        "ready": bool(
            before.decision == "replan_required"
            and revised.state == "active"
            and inspect.state == "completed"
            and alternative.step_id == "alternative"
            and verify.step_id == "verify"
            and final.state == "completed"
            and goal is not None
            and goal.state == "completed"
        ),
        "decision_before_replan": before.decision,
        "completed_step_preserved": inspect.state == "completed",
        "replacement_step": alternative.step_id,
        "final_plan_state": final.state,
        "final_goal_state": goal.state if goal is not None else None,
        "replan_history_count": len(
            final.provenance.get("replan_history", [])
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
