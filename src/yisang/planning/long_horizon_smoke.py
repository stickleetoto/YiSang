from __future__ import annotations

import argparse
import json

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="yisang-long-horizon-smoke"
    )
    parser.parse_args(argv)

    goal_port = InMemoryGoalPort()
    goal_port.put(
        GoalRecord(
            goal_id="goal-demo",
            description="complete durable long-horizon demo",
            state="planned",
        )
    )
    goals = GoalService(goal_port)
    plans = PlanService(InMemoryPlanPort())
    plans.accept_proposal(
        PlanProposal(
            proposal_id="proposal-demo",
            plan_id="plan-demo",
            goal_id="goal-demo",
            proposed_by="planner",
            steps=(
                PlanStepSpec("inspect", "Inspect"),
                PlanStepSpec(
                    "edit",
                    "Edit",
                    depends_on=("inspect",),
                ),
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

    first = bridge.start_next("plan-demo", run_id="run-inspect")
    resume = bridge.assess_resume("plan-demo")
    bridge.complete_step(
        "plan-demo",
        "inspect",
        run_id="run-inspect",
        result_ref="result:inspect",
    )
    second = bridge.start_next("plan-demo", run_id="run-edit")
    final = bridge.complete_step(
        "plan-demo",
        "edit",
        run_id="run-edit",
        result_ref="result:edit",
    )

    goal = goal_port.get("goal-demo")
    payload = {
        "ready": bool(
            first.step_id == "inspect"
            and resume.decision == "recover_running_step"
            and resume.run_id == "run-inspect"
            and second.step_id == "edit"
            and final.state == "completed"
            and goal is not None
            and goal.state == "completed"
        ),
        "first_step": first.step_id,
        "running_resume_decision": resume.decision,
        "running_resume_run_id": resume.run_id,
        "second_step": second.step_id,
        "final_plan_state": final.state,
        "final_goal_state": goal.state if goal is not None else None,
        "plan_revision": final.revision,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
