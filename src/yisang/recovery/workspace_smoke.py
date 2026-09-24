from __future__ import annotations

import argparse
import json
from tempfile import TemporaryDirectory

from yisang.ego.models import EgoManifest
from yisang.execution import (
    ActionGate,
    ActionProposal,
    ToolRegistry,
    register_workspace_write_tools,
)
from yisang.goal import GoalRecord, InMemoryGoalPort
from yisang.policy import AuthorizationPolicyEngine, PolicyRule
from yisang.recovery import (
    CrashRecoveryPlanner,
    DeterministicRecoveryFaultInjector,
    InMemoryCheckpointPort,
    InMemoryRunJournalPort,
    InMemorySideEffectReceiptPort,
    InjectedRecoveryCrash,
    RecoveryAwareActionRuntime,
    RecoveryCoordinator,
    WorkspaceWriteReconciler,
)


def _ego() -> EgoManifest:
    return EgoManifest(
        ego_id="ego.workspace-editor",
        name="Workspace Editor",
        provides=("repository_edit",),
        permissions={"filesystem": "workspace"},
    )


def _gate() -> ActionGate:
    policy = AuthorizationPolicyEngine(
        [
            PolicyRule(
                "permit-state-write",
                "permit",
                principal="ego.workspace-editor",
                action="filesystem.write",
                resource_type="workspace_path",
                resource="state/*",
            )
        ]
    )
    return ActionGate(
        allow_side_effects=True,
        policy_engine=policy,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="yisang-workspace-recovery-smoke"
    )
    parser.parse_args(argv)

    with TemporaryDirectory(prefix="yisang-workspace-recovery-") as temp:
        tools = ToolRegistry()
        register_workspace_write_tools(tools, root=temp)
        journal = InMemoryRunJournalPort()
        receipts = InMemorySideEffectReceiptPort()

        goals = InMemoryGoalPort()
        goals.put(
            GoalRecord(
                goal_id="goal-write-state",
                description="persist a workspace state file",
                state="active",
                next_action="write state/data.txt",
            )
        )
        recovery = RecoveryCoordinator(
            goals=goals,
            journal=journal,
            checkpoints=InMemoryCheckpointPort(),
            side_effects=receipts,
        )

        crashing = RecoveryAwareActionRuntime(
            tools=tools,
            journal=journal,
            side_effects=receipts,
            gate=_gate(),
            fault_injector=DeterministicRecoveryFaultInjector(
                "after_handler_success_before_receipt_commit"
            ),
        )
        proposal = ActionProposal(
            "workspace.write_text",
            {
                "path": "state/data.txt",
                "content": "durable-state",
                "create_parents": True,
            },
            idempotency_key="write-state-data-v1",
        )

        crash_seen = False
        try:
            crashing.execute(
                proposal,
                selected_egos=[_ego()],
                execution_context={
                    "goal_id": "goal-write-state",
                    "run_id": "run-1",
                },
            )
        except InjectedRecoveryCrash:
            crash_seen = True

        directive_before = CrashRecoveryPlanner(recovery).plan(
            "goal-write-state",
            run_id="run-1",
        )
        inspection = WorkspaceWriteReconciler(temp).resolve_if_matches(
            recovery,
            goal_id="goal-write-state",
            idempotency_key="write-state-data-v1",
            run_id="run-2",
        )

        resumed = RecoveryAwareActionRuntime(
            tools=tools,
            journal=journal,
            side_effects=receipts,
            gate=_gate(),
        )
        duplicate = resumed.execute(
            proposal,
            selected_egos=[_ego()],
            execution_context={
                "goal_id": "goal-write-state",
                "run_id": "run-2",
            },
        )
        receipt = receipts.get_receipt(
            "goal-write-state",
            "write-state-data-v1",
        )

        payload = {
            "ready": bool(
                crash_seen
                and directive_before.mode == "reconcile_side_effect"
                and inspection.matches_expected
                and receipt is not None
                and receipt.state == "committed"
                and duplicate.status == "EXECUTED"
                and duplicate.recovered_skip
            ),
            "crash_seen": crash_seen,
            "directive_before_reconcile": directive_before.mode,
            "inspection_status": inspection.status,
            "receipt_state_after_reconcile": (
                receipt.state if receipt is not None else None
            ),
            "duplicate_execution_skipped": duplicate.recovered_skip,
            "duplicate_receipt_id_same": (
                receipt is not None
                and duplicate.side_effect_receipt_id == receipt.receipt_id
            ),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
