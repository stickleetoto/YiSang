from __future__ import annotations

from .models import YiSangRequest, YiSangResponse
from yisang.context.compiler import ContextCompiler
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.router import EngineRouter
from yisang.execution.models import ActionResult
from yisang.execution.runtime import ActionRuntime
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.governor import MemoryGovernor
from yisang.memory.port import MemoryPort
from yisang.verification.base import Verifier


class YiSangRuntime:
    def __init__(
        self,
        *,
        identity: IdentityCharter,
        state: AgentState,
        memory: MemoryPort,
        governor: MemoryGovernor,
        ego_registry: EgoRegistry,
        capability_router: CapabilityRouter,
        context_compiler: ContextCompiler,
        engine_router: EngineRouter,
        verifier: Verifier,
        action_runtime: ActionRuntime | None = None,
        max_action_rounds: int = 3,
    ) -> None:
        if max_action_rounds < 0:
            raise ValueError("max_action_rounds must be non-negative")

        self.identity = identity
        self.state = state
        self.memory = memory
        self.governor = governor
        self.ego_registry = ego_registry
        self.capability_router = capability_router
        self.context_compiler = context_compiler
        self.engine_router = engine_router
        self.verifier = verifier
        self.action_runtime = action_runtime
        self.max_action_rounds = max_action_rounds

    def run(self, request: YiSangRequest) -> YiSangResponse:
        memories = self.memory.search(request.text, limit=8)
        selected_egos = self.capability_router.route(
            request.text,
            self.ego_registry.list_all(),
            limit=3,
        )
        available_tools = (
            self.action_runtime.available_tools(selected_egos=selected_egos)
            if self.action_runtime is not None
            else []
        )

        engine = self.engine_router.get(self.state.active_engine)
        action_results: list[ActionResult] = []
        action_history: list[dict] = []
        loop_exhausted = False

        for action_round in range(self.max_action_rounds + 1):
            context = self.context_compiler.compile(
                request=request,
                identity=self.identity,
                state=self.state,
                memories=memories,
                egos=selected_egos,
                tools=available_tools,
                action_history=action_history,
            )
            result = engine.generate(context)

            if not result.action_proposals:
                break

            if action_round >= self.max_action_rounds:
                loop_exhausted = True
                for proposal in result.action_proposals:
                    denied = ActionResult(
                        tool_id=proposal.action,
                        status="DENIED",
                        gate_reason="action_loop_limit",
                    )
                    action_results.append(denied)
                    action_history.append(_history_item(proposal, denied))
                break

            round_failed = False
            for proposal in result.action_proposals:
                if self.action_runtime is None:
                    executed = ActionResult(
                        tool_id=proposal.action,
                        status="DENIED",
                        gate_reason="action_runtime_not_configured",
                    )
                else:
                    executed = self.action_runtime.execute(
                        proposal,
                        selected_egos=selected_egos,
                    )

                action_results.append(executed)
                action_history.append(_history_item(proposal, executed))

                if executed.status != "EXECUTED":
                    round_failed = True

            if round_failed:
                break

            # Preserve one-shot behavior for legacy engines. Only engines that
            # explicitly support action feedback receive another reasoning turn.
            if not getattr(engine, "supports_action_feedback", False):
                break

        if action_results or loop_exhausted:
            result.metadata = dict(result.metadata)
            result.metadata["action_results"] = [
                item.to_dict() for item in action_results
            ]
            if loop_exhausted:
                result.metadata["action_loop_exhausted"] = True

        verification = self.verifier.verify(
            request=request,
            engine_result=result,
        )

        if verification.status == "PASS" and result.memory_proposals:
            for proposal in result.memory_proposals:
                decision = self.governor.evaluate(proposal, self.memory)
                if decision.accepted:
                    self.memory.commit(proposal)

        return YiSangResponse(
            request_id=request.request_id,
            text=result.text,
            engine_id=result.engine_id,
            verification_status=verification.status,
            used_memory_ids=[m.memory_id for m in memories],
            used_ego_ids=[e.ego_id for e in selected_egos],
            action_results=[item.to_dict() for item in action_results],
        )


def _history_item(proposal, result: ActionResult) -> dict:
    return {
        "requested_action": {
            "tool_id": proposal.action,
            "arguments": dict(proposal.arguments),
            "requested_by": proposal.requested_by,
        },
        "result": result.to_dict(),
    }
