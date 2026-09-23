from __future__ import annotations

from yisang.ego.models import EgoManifest
from yisang.execution.completion import ToolOutcome
from yisang.execution.failure import (
    failure_from_exception,
    failure_from_gate_reason,
)
from yisang.execution.models import ActionProposal, ActionResult
from yisang.execution.runtime import ActionRuntime
from yisang.execution.tools import ToolRegistry
from yisang.execution.gate import ActionGate

from .idempotency import side_effect_request_digest, side_effect_result_ref
from .port import RunJournalPort, SideEffectReceiptPort


class RecoveryAwareActionRuntime(ActionRuntime):
    """ActionRuntime with durable side-effect receipts and journal evidence."""

    def __init__(
        self,
        *,
        tools: ToolRegistry,
        journal: RunJournalPort,
        side_effects: SideEffectReceiptPort,
        gate: ActionGate | None = None,
    ) -> None:
        super().__init__(tools=tools, gate=gate)
        self.journal = journal
        self.side_effects = side_effects

    def execute(
        self,
        proposal: ActionProposal,
        *,
        selected_egos: list[EgoManifest],
        execution_context: dict[str, str] | None = None,
    ) -> ActionResult:
        context = dict(execution_context or {})
        goal_id = context.get("goal_id")
        run_id = context.get("run_id")
        tool = self.tools.get(proposal.action) if self.tools.has(proposal.action) else None
        digest = side_effect_request_digest(
            proposal.action,
            dict(proposal.arguments),
        )

        if goal_id and run_id:
            self.journal.append(
                goal_id,
                run_id,
                "action_proposed",
                payload={
                    "tool_id": proposal.action,
                    "request_digest": digest,
                    "idempotency_key": proposal.idempotency_key,
                },
            )

        decision = self.gate.evaluate(
            proposal,
            selected_egos=selected_egos,
            tools=self.tools,
        )
        if not decision.allowed:
            if goal_id and run_id:
                self.journal.append(
                    goal_id,
                    run_id,
                    "action_authorized",
                    payload={
                        "tool_id": proposal.action,
                        "allowed": False,
                        "reason": decision.reason,
                    },
                )
            return ActionResult(
                tool_id=proposal.action,
                status="DENIED",
                gate_reason=decision.reason,
                ego_id=decision.ego_id,
                failure=failure_from_gate_reason(
                    decision.reason,
                    tool_id=proposal.action,
                ),
            )

        assert tool is not None
        if goal_id and run_id:
            self.journal.append(
                goal_id,
                run_id,
                "action_authorized",
                payload={
                    "tool_id": proposal.action,
                    "allowed": True,
                    "ego_id": decision.ego_id,
                },
            )

        try:
            tool.validate_arguments(dict(proposal.arguments))
        except Exception as exc:
            return self._error(
                proposal,
                decision.reason,
                decision.ego_id,
                exc,
                goal_id=goal_id,
                run_id=run_id,
            )

        receipt = None
        if tool.side_effecting:
            if not goal_id or not run_id:
                return self._denied(
                    proposal,
                    "missing_recovery_context",
                    decision.ego_id,
                )
            key = (proposal.idempotency_key or "").strip()
            if not key:
                return self._denied(
                    proposal,
                    "missing_idempotency_key",
                    decision.ego_id,
                )

            existing = self.side_effects.get_receipt(goal_id, key)
            if existing is not None:
                if existing.request_digest != digest:
                    return self._denied(
                        proposal,
                        "recovery_idempotency_conflict",
                        decision.ego_id,
                    )
                if existing.state == "committed":
                    self.journal.append(
                        goal_id,
                        run_id,
                        "recovery_decision",
                        payload={
                            "decision": "skip",
                            "reason": "side_effect_already_committed",
                            "receipt_id": existing.receipt_id,
                        },
                    )
                    return ActionResult(
                        tool_id=proposal.action,
                        status="EXECUTED",
                        output={"result_ref": existing.result_ref},
                        gate_reason="recovery_already_committed",
                        ego_id=decision.ego_id,
                        completion_evidence={
                            "side_effect_receipt_id": existing.receipt_id,
                            "result_ref": existing.result_ref,
                        },
                        side_effect_receipt_id=existing.receipt_id,
                        recovered_skip=True,
                    )
                if existing.state == "started":
                    return self._denied(
                        proposal,
                        "recovery_uncertain_side_effect",
                        decision.ego_id,
                        receipt_id=existing.receipt_id,
                    )
                return self._denied(
                    proposal,
                    "recovery_retry_required",
                    decision.ego_id,
                    receipt_id=existing.receipt_id,
                )

            receipt = self.side_effects.reserve(
                goal_id=goal_id,
                run_id=run_id,
                idempotency_key=key,
                tool_id=proposal.action,
                request_digest=digest,
                metadata={"requested_by": proposal.requested_by},
            )
            self.journal.append(
                goal_id,
                run_id,
                "side_effect_reserved",
                payload={
                    "receipt_id": receipt.receipt_id,
                    "tool_id": proposal.action,
                    "idempotency_key": key,
                    "request_digest": digest,
                },
            )

        try:
            raw_output = tool.handler(dict(proposal.arguments))
            if isinstance(raw_output, ToolOutcome):
                output = raw_output.output
                goal_satisfied = raw_output.goal_satisfied
                completion_text = raw_output.completion_text
                completion_evidence = dict(raw_output.evidence)
            else:
                output = raw_output
                goal_satisfied = False
                completion_text = None
                completion_evidence = {}
        except Exception as exc:
            if receipt is not None:
                failed = self.side_effects.fail_receipt(
                    receipt.receipt_id,
                    reason=f"{type(exc).__name__}: {exc}",
                )
                self.journal.append(
                    goal_id,
                    run_id,
                    "side_effect_failed",
                    payload={
                        "receipt_id": failed.receipt_id,
                        "tool_id": proposal.action,
                        "reason": failed.failure_reason,
                    },
                )
            return self._error(
                proposal,
                decision.reason,
                decision.ego_id,
                exc,
                goal_id=goal_id,
                run_id=run_id,
                receipt_id=receipt.receipt_id if receipt is not None else None,
            )

        result_ref = None
        if receipt is not None:
            result_ref = side_effect_result_ref(proposal.action, output)
            committed = self.side_effects.commit_receipt(
                receipt.receipt_id,
                result_ref=result_ref,
            )
            self.journal.append(
                goal_id,
                run_id,
                "side_effect_committed",
                payload={
                    "receipt_id": committed.receipt_id,
                    "tool_id": proposal.action,
                    "result_ref": result_ref,
                },
            )
            completion_evidence["side_effect_receipt_id"] = committed.receipt_id
            completion_evidence["result_ref"] = result_ref

        if goal_id and run_id:
            self.journal.append(
                goal_id,
                run_id,
                "action_executed",
                payload={
                    "tool_id": proposal.action,
                    "status": "EXECUTED",
                    "receipt_id": (
                        receipt.receipt_id if receipt is not None else None
                    ),
                },
            )

        return ActionResult(
            tool_id=proposal.action,
            status="EXECUTED",
            output=output,
            gate_reason=decision.reason,
            ego_id=decision.ego_id,
            goal_satisfied=goal_satisfied,
            completion_text=completion_text,
            completion_evidence=completion_evidence,
            side_effect_receipt_id=(
                receipt.receipt_id if receipt is not None else None
            ),
        )

    def _denied(
        self,
        proposal: ActionProposal,
        reason: str,
        ego_id: str | None,
        *,
        receipt_id: str | None = None,
    ) -> ActionResult:
        return ActionResult(
            tool_id=proposal.action,
            status="DENIED",
            gate_reason=reason,
            ego_id=ego_id,
            failure=failure_from_gate_reason(
                reason,
                tool_id=proposal.action,
            ),
            side_effect_receipt_id=receipt_id,
        )

    def _error(
        self,
        proposal: ActionProposal,
        gate_reason: str,
        ego_id: str | None,
        exc: Exception,
        *,
        goal_id: str | None,
        run_id: str | None,
        receipt_id: str | None = None,
    ) -> ActionResult:
        if goal_id and run_id:
            self.journal.append(
                goal_id,
                run_id,
                "action_executed",
                payload={
                    "tool_id": proposal.action,
                    "status": "ERROR",
                    "error_type": type(exc).__name__,
                    "receipt_id": receipt_id,
                },
            )
        return ActionResult(
            tool_id=proposal.action,
            status="ERROR",
            error=f"{type(exc).__name__}: {exc}",
            gate_reason=gate_reason,
            ego_id=ego_id,
            failure=failure_from_exception(
                exc,
                tool_id=proposal.action,
            ),
            side_effect_receipt_id=receipt_id,
        )
