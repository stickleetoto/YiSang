from __future__ import annotations

import argparse
import json

from .in_memory import InMemoryPlanPort
from .models import PlanProposal, PlanStepSpec
from .scheduler import LongHorizonScheduler
from .service import PlanService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yisang-planner-smoke")
    parser.parse_args(argv)

    service = PlanService(InMemoryPlanPort())
    proposal = PlanProposal(
        proposal_id="proposal-demo",
        plan_id="plan-demo",
        goal_id="goal-demo",
        proposed_by="planner-engine",
        steps=(
            PlanStepSpec(
                "inspect",
                "Inspect repository",
                priority=10,
            ),
            PlanStepSpec(
                "edit",
                "Apply minimal edit",
                depends_on=("inspect",),
                max_attempts=2,
            ),
            PlanStepSpec(
                "verify",
                "Verify result",
                depends_on=("edit",),
            ),
        ),
    )
    accepted = service.accept_proposal(
        proposal,
        actor="human-reviewer",
        reason="approved deterministic demo plan",
    )
    scheduler = LongHorizonScheduler(service)

    first = scheduler.decide("plan-demo")
    service.start_step("plan-demo", first.step_id)
    service.complete_step(
        "plan-demo",
        "inspect",
        result_ref="result:inspect",
    )
    second = scheduler.decide("plan-demo")
    service.start_step("plan-demo", second.step_id)
    service.complete_step(
        "plan-demo",
        "edit",
        result_ref="result:edit",
    )
    third = scheduler.decide("plan-demo")
    service.start_step("plan-demo", third.step_id)
    final = service.complete_step(
        "plan-demo",
        "verify",
        result_ref="result:verify",
    )

    payload = {
        "ready": bool(
            accepted.revision == 1
            and first.step_id == "inspect"
            and second.step_id == "edit"
            and third.step_id == "verify"
            and final.state == "completed"
            and final.revision == 7
        ),
        "accepted_revision": accepted.revision,
        "step_order": [
            first.step_id,
            second.step_id,
            third.step_id,
        ],
        "final_state": final.state,
        "final_revision": final.revision,
        "history_length": len(service.port.history("plan-demo")),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
