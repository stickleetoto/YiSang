from __future__ import annotations

from yisang.execution import ActionGate, ActionProposal, ToolRegistry
from yisang.execution.builtin import register_workspace_write_tools
from yisang.ego.models import EgoManifest
from yisang.goal import GoalRecord, InMemoryGoalPort
from yisang.recovery import (
    DeterministicRecoveryFaultInjector,
    InMemoryCheckpointPort,
    InMemoryRunJournalPort,
    InMemorySideEffectReceiptPort,
    InjectedRecoveryCrash,
    RecoveryAwareActionRuntime,
    RecoveryCoordinator,
    WorkspaceWriteReconciler,
)


def _ego():
    return EgoManifest(
        ego_id="ego.editor",
        name="Editor",
        provides=("repository_edit",),
        permissions={"filesystem": "workspace"},
    )


def test_workspace_reconciler_confirms_written_uncertain_receipt(tmp_path):
    tools = ToolRegistry()
    register_workspace_write_tools(tools, root=tmp_path)
    journal = InMemoryRunJournalPort()
    receipts = InMemorySideEffectReceiptPort()
    runtime = RecoveryAwareActionRuntime(
        tools=tools,
        journal=journal,
        side_effects=receipts,
        gate=ActionGate(allow_side_effects=True),
        fault_injector=DeterministicRecoveryFaultInjector(
            "after_handler_success_before_receipt_commit"
        ),
    )

    try:
        runtime.execute(
            ActionProposal(
                "workspace.write_text",
                {"path": "state.txt", "content": "target-state"},
                idempotency_key="state-write",
            ),
            selected_egos=[_ego()],
            execution_context={"goal_id": "g1", "run_id": "r1"},
        )
    except InjectedRecoveryCrash:
        pass

    goals = InMemoryGoalPort()
    goals.put(
        GoalRecord(
            goal_id="g1",
            description="write state",
            state="active",
            next_action="verify state",
        )
    )
    recovery = RecoveryCoordinator(
        goals=goals,
        journal=journal,
        checkpoints=InMemoryCheckpointPort(),
        side_effects=receipts,
    )

    inspection = WorkspaceWriteReconciler(tmp_path).resolve_if_matches(
        recovery,
        goal_id="g1",
        idempotency_key="state-write",
        run_id="r2",
    )

    assert inspection.matches_expected is True
    receipt = receipts.get_receipt("g1", "state-write")
    assert receipt is not None
    assert receipt.state == "committed"
    assert receipt.evidence_refs
