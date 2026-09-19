from __future__ import annotations

from yisang.ego.models import EgoManifest

from .completion import ToolOutcome
from .failure import failure_from_exception, failure_from_gate_reason
from .gate import ActionGate
from .models import ActionProposal, ActionResult
from .tools import ToolRegistry


class ActionRuntime:
    def __init__(self, *, tools: ToolRegistry, gate: ActionGate | None = None) -> None:
        self.tools = tools
        self.gate = gate or ActionGate()

    def available_tools(
        self,
        *,
        selected_egos: list[EgoManifest],
    ) -> list[dict]:
        specs: list[dict] = []
        for tool in self.tools.list_all():
            decision = self.gate.evaluate(
                ActionProposal(action=tool.tool_id),
                selected_egos=selected_egos,
                tools=self.tools,
            )
            if decision.allowed:
                specs.append(tool.to_context_spec(ego_id=decision.ego_id))
        return specs

    def execute(
        self,
        proposal: ActionProposal,
        *,
        selected_egos: list[EgoManifest],
    ) -> ActionResult:
        decision = self.gate.evaluate(
            proposal,
            selected_egos=selected_egos,
            tools=self.tools,
        )
        if not decision.allowed:
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

        tool = self.tools.get(proposal.action)
        try:
            tool.validate_arguments(dict(proposal.arguments))
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
            return ActionResult(
                tool_id=proposal.action,
                status="ERROR",
                error=f"{type(exc).__name__}: {exc}",
                gate_reason=decision.reason,
                ego_id=decision.ego_id,
                failure=failure_from_exception(
                    exc,
                    tool_id=proposal.action,
                ),
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
        )
