from __future__ import annotations

from .models import YiSangRequest, YiSangResponse
from yisang.context.compiler import ContextCompiler
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.router import EngineRouter
from yisang.execution.failure import failure_from_gate_reason
from yisang.execution.models import ActionResult
from yisang.execution.runtime import ActionRuntime
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.governor import MemoryGovernor
from yisang.memory.pipeline import MemoryWritePipeline
from yisang.memory.port import MemoryPort
from yisang.memory.quarantine import InMemoryQuarantinePort
from yisang.session.port import SessionPort
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
        memory_pipeline: MemoryWritePipeline | None = None,
        session_port: SessionPort | None = None,
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
        self.session_port = session_port
        self.memory_pipeline = memory_pipeline or MemoryWritePipeline(
            memory=memory,
            governor=governor,
            quarantine=InMemoryQuarantinePort(),
        )
        self.max_action_rounds = max_action_rounds

    def run(self, request: YiSangRequest) -> YiSangResponse:
        session_id = _session_id(request)
        session_history = (
            self.session_port.history(
                session_id,
                limit=self.context_compiler.budget.max_session_messages,
            )
            if self.session_port is not None and session_id is not None
            else []
        )

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
        goal_satisfied = False
        completion_text: str | None = None
        completion_evidence: dict = {}

        for action_round in range(self.max_action_rounds + 1):
            context = self.context_compiler.compile(
                request=request,
                identity=self.identity,
                state=self.state,
                memories=memories,
                egos=selected_egos,
                tools=available_tools,
                action_history=action_history,
                session_history=session_history,
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
                        failure=failure_from_gate_reason(
                            "action_loop_limit",
                            tool_id=proposal.action,
                        ),
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
                        failure=failure_from_gate_reason(
                            "action_runtime_not_configured",
                            tool_id=proposal.action,
                        ),
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
                elif executed.goal_satisfied:
                    goal_satisfied = True
                    if executed.completion_text:
                        completion_text = executed.completion_text
                    completion_evidence.update(executed.completion_evidence)

            if round_failed:
                break

            if goal_satisfied:
                result.text = completion_text or "Completed requested action."
                result.metadata = dict(result.metadata)
                result.metadata["goal_satisfied"] = True
                result.metadata["completion_evidence"] = dict(completion_evidence)
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

        if memories:
            self.memory.record_outcome(
                [memory.memory_id for memory in memories],
                success=(verification.status == "PASS"),
            )

        memory_write_results: list[dict] = []
        if verification.status == "PASS" and result.memory_proposals:
            for proposal in result.memory_proposals:
                write_result = self.memory_pipeline.submit(proposal)
                memory_write_results.append({
                    "status": write_result.status.value,
                    "reason": write_result.reason,
                    "memory_id": (
                        write_result.record.memory_id
                        if write_result.record is not None
                        else None
                    ),
                    "quarantine_id": (
                        write_result.quarantine.quarantine_id
                        if write_result.quarantine is not None
                        else None
                    ),
                    "risk_flags": list(write_result.risk_flags),
                })

        if self.session_port is not None and session_id is not None:
            self.session_port.append(
                session_id,
                role="user",
                content=request.text,
                metadata={"request_id": request.request_id},
            )
            self.session_port.append(
                session_id,
                role="assistant",
                content=result.text,
                metadata={
                    "request_id": request.request_id,
                    "engine_id": result.engine_id,
                    "verification_status": verification.status,
                },
            )

        return YiSangResponse(
            request_id=request.request_id,
            text=result.text,
            engine_id=result.engine_id,
            verification_status=verification.status,
            used_memory_ids=[m.memory_id for m in memories],
            used_ego_ids=[e.ego_id for e in selected_egos],
            action_results=[item.to_dict() for item in action_results],
            memory_write_results=memory_write_results,
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


def _session_id(request: YiSangRequest) -> str | None:
    value = request.metadata.get("session_id")
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None
