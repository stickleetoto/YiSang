from __future__ import annotations

import time

from .models import YiSangRequest, YiSangResponse
from yisang.context.compiler import ContextCompiler
from yisang.ego.registry import EgoRegistry
from yisang.ego.telemetry import EgoTelemetryEvent, EgoTelemetryPort
from yisang.ego.router import CapabilityRouter
from yisang.engines.router import EngineRouter
from yisang.execution.failure import failure_from_gate_reason
from yisang.execution.models import ActionResult
from yisang.execution.runtime import ActionRuntime
from yisang.experience.episode_port import ExperiencePort
from yisang.experience.recorder import ExperienceRecorder
from yisang.experience.trace import ActionTraceRecorder
from yisang.experience.trace_port import ActionTracePort
from yisang.identity.models import AgentState, IdentityCharter
from yisang.library.delivery import build_library_delivery
from yisang.library.port import LibraryPort
from yisang.library.retrieval import LexicalLibraryRetriever
from yisang.memory.governor import MemoryGovernor
from yisang.memory.pipeline import MemoryWritePipeline
from yisang.memory.port import MemoryPort
from yisang.memory.quarantine import InMemoryQuarantinePort
from yisang.recovery.port import RunJournalPort
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
        library_port: LibraryPort | None = None,
        library_retriever: LexicalLibraryRetriever | None = None,
        experience_port: ExperiencePort | None = None,
        experience_recorder: ExperienceRecorder | None = None,
        experience_trace_port: ActionTracePort | None = None,
        experience_trace_recorder: ActionTraceRecorder | None = None,
        ego_telemetry_port: EgoTelemetryPort | None = None,
        run_journal_port: RunJournalPort | None = None,
        library_limit: int = 3,
        max_action_rounds: int = 3,
    ) -> None:
        if max_action_rounds < 0:
            raise ValueError("max_action_rounds must be non-negative")
        if library_limit <= 0:
            raise ValueError("library_limit must be positive")

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

        if library_port is None and library_retriever is not None:
            library_port = library_retriever.port
        if (
            library_port is not None
            and library_retriever is not None
            and library_retriever.port is not library_port
        ):
            raise ValueError(
                "library_retriever must be backed by runtime library_port"
            )
        if library_port is not None and library_retriever is None:
            library_retriever = LexicalLibraryRetriever(library_port)

        self.library_port = library_port
        self.library_retriever = library_retriever
        self.experience_port = experience_port
        self.experience_recorder = experience_recorder or ExperienceRecorder()
        self.experience_trace_port = experience_trace_port
        self.experience_trace_recorder = (
            experience_trace_recorder or ActionTraceRecorder()
        )
        self.ego_telemetry_port = ego_telemetry_port
        if (
            run_journal_port is None
            and action_runtime is not None
            and hasattr(action_runtime, "journal")
        ):
            run_journal_port = getattr(action_runtime, "journal")
        if (
            run_journal_port is not None
            and action_runtime is not None
            and hasattr(action_runtime, "journal")
            and getattr(action_runtime, "journal") is not run_journal_port
        ):
            raise ValueError(
                "run_journal_port must match recovery-aware ActionRuntime journal"
            )
        self.run_journal_port = run_journal_port
        self.library_limit = library_limit
        self.memory_pipeline = memory_pipeline or MemoryWritePipeline(
            memory=memory,
            governor=governor,
            quarantine=InMemoryQuarantinePort(),
        )
        self.max_action_rounds = max_action_rounds

    def run(self, request: YiSangRequest) -> YiSangResponse:
        run_started = time.perf_counter()
        session_id = _session_id(request)
        goal_run = _goal_run_context(request)
        goal_id = goal_run[0] if goal_run is not None else None
        run_id = goal_run[1] if goal_run is not None else None
        if (
            self.run_journal_port is not None
            and goal_id is not None
            and run_id is not None
            and self.run_journal_port.latest_sequence(goal_id, run_id) == 0
        ):
            self.run_journal_port.append(
                goal_id,
                run_id,
                "goal_started",
                payload={"request_id": request.request_id},
            )
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
        library_payload = ()
        if self.library_retriever is not None and request.text.strip():
            library_results = self.library_retriever.search(
                request.text,
                limit=self.library_limit,
            )
            library_payload = build_library_delivery(
                library_results,
                request=request.text,
                max_chars=self.context_compiler.budget.max_library_chars,
            )

        engine = self.engine_router.get(self.state.active_engine)
        action_results: list[ActionResult] = []
        action_history: list[dict] = []
        experience_trace_ids: list[str] = []
        action_trace_ordinal = 0
        used_knowledge_refs: list[str] = []
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
                library=library_payload,
                tools=available_tools,
                action_history=action_history,
                session_history=session_history,
            )
            for item in context.library:
                knowledge_ref = item.get("knowledge_ref")
                if knowledge_ref and knowledge_ref not in used_knowledge_refs:
                    used_knowledge_refs.append(str(knowledge_ref))

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
                    if self.experience_trace_port is not None:
                        trace = self.experience_trace_recorder.record(
                            request_id=request.request_id,
                            ordinal=action_trace_ordinal,
                            proposal=proposal,
                            result=denied,
                        )
                        self.experience_trace_port.put_trace(trace)
                        experience_trace_ids.append(trace.trace_id)
                        action_trace_ordinal += 1
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
                        execution_context=(
                            {"goal_id": goal_id, "run_id": run_id}
                            if goal_id is not None and run_id is not None
                            else None
                        ),
                    )

                action_results.append(executed)
                action_history.append(_history_item(proposal, executed))
                if self.experience_trace_port is not None:
                    trace = self.experience_trace_recorder.record(
                        request_id=request.request_id,
                        ordinal=action_trace_ordinal,
                        proposal=proposal,
                        result=executed,
                    )
                    self.experience_trace_port.put_trace(trace)
                    experience_trace_ids.append(trace.trace_id)
                    action_trace_ordinal += 1

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
        if (
            self.run_journal_port is not None
            and goal_id is not None
            and run_id is not None
        ):
            self.run_journal_port.append(
                goal_id,
                run_id,
                "verification_result",
                payload={
                    "request_id": request.request_id,
                    "status": verification.status,
                    "reason": verification.reason,
                },
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

        ego_telemetry_event_ids: list[str] = []
        if self.ego_telemetry_port is not None and selected_egos:
            latency_ms = (time.perf_counter() - run_started) * 1000.0
            action_failure_count = sum(
                item.status != "EXECUTED" for item in action_results
            )
            success = (
                verification.status == "PASS"
                and action_failure_count == 0
            )
            for ego in selected_egos:
                event = self.ego_telemetry_port.record(
                    EgoTelemetryEvent.runtime_use(
                        ego_id=ego.ego_id,
                        version=getattr(ego, "version", "1.0.0"),
                        request_id=request.request_id,
                        success=success,
                        verification_status=verification.status,
                        latency_ms=latency_ms,
                        action_failure_count=action_failure_count,
                    )
                )
                ego_telemetry_event_ids.append(event.event_id)

        response = YiSangResponse(
            request_id=request.request_id,
            text=result.text,
            engine_id=result.engine_id,
            verification_status=verification.status,
            used_memory_ids=[m.memory_id for m in memories],
            used_ego_ids=[e.ego_id for e in selected_egos],
            used_knowledge_refs=used_knowledge_refs,
            action_results=[item.to_dict() for item in action_results],
            memory_write_results=memory_write_results,
            experience_trace_ids=experience_trace_ids,
            ego_telemetry_event_ids=ego_telemetry_event_ids,
            goal_id=goal_id,
            run_id=run_id,
            run_journal_sequence=(
                self.run_journal_port.latest_sequence(goal_id, run_id)
                if (
                    self.run_journal_port is not None
                    and goal_id is not None
                    and run_id is not None
                )
                else None
            ),
        )
        if self.experience_port is not None:
            episode = self.experience_recorder.capture(
                request_id=request.request_id, request_text=request.text,
                request_metadata=request.metadata, engine_id=result.engine_id,
                verification_status=verification.status, verification_reason=verification.reason,
                action_results=action_results, memories=memories, library_payload=library_payload,
            )
            self.experience_port.put_episode(episode)
            response.experience_episode_id = episode.episode_id
        return response


def _history_item(proposal, result: ActionResult) -> dict:
    return {
        "requested_action": {
            "tool_id": proposal.action,
            "arguments": dict(proposal.arguments),
            "requested_by": proposal.requested_by,
            "idempotency_key": proposal.idempotency_key,
        },
        "result": result.to_dict(),
    }


def _session_id(request: YiSangRequest) -> str | None:
    value = request.metadata.get("session_id")
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None



def _goal_run_context(request: YiSangRequest) -> tuple[str, str] | None:
    raw_goal = request.metadata.get("goal_id")
    raw_run = request.metadata.get("run_id")
    if raw_goal is None and raw_run is None:
        return None
    if not isinstance(raw_goal, str) or not raw_goal.strip():
        raise ValueError("goal_id must be a non-empty string when run_id is set")
    if not isinstance(raw_run, str) or not raw_run.strip():
        raise ValueError("run_id must be a non-empty string when goal_id is set")
    return raw_goal.strip(), raw_run.strip()
