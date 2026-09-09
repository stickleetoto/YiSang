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
    ) -> None:
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

    def run(self, request: YiSangRequest) -> YiSangResponse:
        memories = self.memory.search(request.text, limit=8)
        selected_egos = self.capability_router.route(
            request.text,
            self.ego_registry.list_all(),
            limit=3,
        )
        context = self.context_compiler.compile(
            request=request,
            identity=self.identity,
            state=self.state,
            memories=memories,
            egos=selected_egos,
        )

        engine = self.engine_router.get(self.state.active_engine)
        result = engine.generate(context)

        action_results: list[ActionResult] = []
        for proposal in result.action_proposals:
            if self.action_runtime is None:
                action_results.append(
                    ActionResult(
                        tool_id=proposal.action,
                        status="DENIED",
                        gate_reason="action_runtime_not_configured",
                    )
                )
                continue

            action_results.append(
                self.action_runtime.execute(
                    proposal,
                    selected_egos=selected_egos,
                )
            )

        if action_results:
            result.metadata = dict(result.metadata)
            result.metadata["action_results"] = [
                item.to_dict() for item in action_results
            ]

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
