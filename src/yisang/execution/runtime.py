from __future__ import annotations

from yisang.ego.models import EgoManifest

from .gate import ActionGate
from .models import ActionProposal, ActionResult
from .tools import ToolRegistry


class ActionRuntime:
    def __init__(self, *, tools: ToolRegistry, gate: ActionGate | None = None) -> None:
        self.tools = tools
        self.gate = gate or ActionGate()

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
            )

        tool = self.tools.get(proposal.action)
        try:
            output = tool.handler(dict(proposal.arguments))
        except Exception as exc:
            return ActionResult(
                tool_id=proposal.action,
                status="ERROR",
                error=f"{type(exc).__name__}: {exc}",
                gate_reason=decision.reason,
                ego_id=decision.ego_id,
            )

        return ActionResult(
            tool_id=proposal.action,
            status="EXECUTED",
            output=output,
            gate_reason=decision.reason,
            ego_id=decision.ego_id,
        )
