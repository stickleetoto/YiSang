from __future__ import annotations

import sys

from yisang.context.compiler import ContextCompiler
from yisang.core.models import YiSangRequest
from yisang.core.runtime import YiSangRuntime
from yisang.ego.models import EgoManifest
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.base import EngineResult, LLMEngine
from yisang.engines.router import EngineRouter
from yisang.execution.completion import ToolOutcome
from yisang.execution.models import ActionProposal
from yisang.execution.runtime import ActionRuntime
from yisang.execution.tools import ToolDefinition, ToolRegistry
from yisang.experience import InMemoryActionTracePort
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.verification.base import PassThroughVerifier


class OneToolEngine(LLMEngine):
    engine_id = "trace-engine"

    def generate(self, context):
        return EngineResult(
            engine_id=self.engine_id,
            text="tool requested",
            action_proposals=[
                ActionProposal("python.replay", {"secret": "runtime-private"})
            ],
        )


def test_runtime_records_replayable_action_trace() -> None:
    tools = ToolRegistry()
    tools.register(
        ToolDefinition(
            tool_id="python.replay",
            handler=lambda _args: ToolOutcome(
                output="ok",
                goal_satisfied=True,
                completion_text="done",
                evidence={
                    "replay_manifest": {
                        "version": 1,
                        "argv": [sys.executable, "-c", "print('ok')"],
                        "stdout_contains": ["ok"],
                    }
                },
            ),
            required_capabilities=("python_replay",),
        )
    )
    egos = EgoRegistry()
    egos.register(
        EgoManifest(
            ego_id="ego.python.replay",
            name="Python Replay",
            provides=("python_replay",),
            keywords=("python",),
        )
    )
    engines = EngineRouter()
    engines.register(OneToolEngine())
    traces = InMemoryActionTracePort()

    runtime = YiSangRuntime(
        identity=IdentityCharter("trace-runtime", "YiSang"),
        state=AgentState(active_engine="trace-engine"),
        memory=InMemoryMemoryPort(),
        governor=MemoryGovernor(),
        ego_registry=egos,
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
        verifier=PassThroughVerifier(),
        action_runtime=ActionRuntime(tools=tools),
        experience_trace_port=traces,
    )
    response = runtime.run(
        YiSangRequest("trace-runtime-request", "python replay")
    )

    assert len(response.experience_trace_ids) == 1
    trace = traces.get_trace(response.experience_trace_ids[0])
    assert trace is not None
    assert trace.replayable is True
    assert trace.tool_id == "python.replay"
    assert "runtime-private" not in repr(trace)
