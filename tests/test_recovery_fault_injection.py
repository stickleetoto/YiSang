from __future__ import annotations

import pytest

from yisang.ego.models import EgoManifest
from yisang.execution import ActionGate, ActionProposal, ToolRegistry
from yisang.execution.builtin import register_workspace_write_tools
from yisang.recovery import (
    DeterministicRecoveryFaultInjector,
    InMemoryRunJournalPort,
    InMemorySideEffectReceiptPort,
    InjectedRecoveryCrash,
    RecoveryAwareActionRuntime,
)


def _ego():
    return EgoManifest(
        ego_id="ego.editor",
        name="Editor",
        provides=("repository_edit",),
        permissions={"filesystem": "workspace"},
    )


def test_crash_after_handler_leaves_started_receipt_and_written_file(tmp_path):
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

    with pytest.raises(InjectedRecoveryCrash):
        runtime.execute(
            ActionProposal(
                "workspace.write_text",
                {"path": "state.txt", "content": "written"},
                idempotency_key="write-state-v1",
            ),
            selected_egos=[_ego()],
            execution_context={"goal_id": "g1", "run_id": "r1"},
        )

    receipt = receipts.get_receipt("g1", "write-state-v1")
    assert receipt is not None
    assert receipt.state == "started"
    assert (tmp_path / "state.txt").read_text(encoding="utf-8") == "written"


def test_committed_receipt_skips_duplicate_handler(tmp_path):
    tools = ToolRegistry()
    register_workspace_write_tools(tools, root=tmp_path)
    journal = InMemoryRunJournalPort()
    receipts = InMemorySideEffectReceiptPort()
    runtime = RecoveryAwareActionRuntime(
        tools=tools,
        journal=journal,
        side_effects=receipts,
        gate=ActionGate(allow_side_effects=True),
    )
    proposal = ActionProposal(
        "workspace.write_text",
        {"path": "state.txt", "content": "once"},
        idempotency_key="write-once",
    )

    first = runtime.execute(
        proposal,
        selected_egos=[_ego()],
        execution_context={"goal_id": "g1", "run_id": "r1"},
    )
    second = runtime.execute(
        proposal,
        selected_egos=[_ego()],
        execution_context={"goal_id": "g1", "run_id": "r2"},
    )

    assert first.status == "EXECUTED"
    assert second.status == "EXECUTED"
    assert second.recovered_skip is True
    assert first.side_effect_receipt_id == second.side_effect_receipt_id
