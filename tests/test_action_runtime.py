from yisang.ego.models import EgoManifest
from yisang.execution.models import ActionProposal
from yisang.execution.runtime import ActionRuntime
from yisang.execution.tools import ToolDefinition, ToolRegistry


def _ego():
    return EgoManifest(
        ego_id="ego.text",
        name="Text",
        provides=("text_stats",),
        permissions={},
    )


def test_action_runtime_executes_authorized_tool():
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            tool_id="text.length",
            handler=lambda args: len(args["text"]),
            required_capabilities=("text_stats",),
        )
    )
    result = ActionRuntime(tools=registry).execute(
        ActionProposal("text.length", {"text": "abc"}),
        selected_egos=[_ego()],
    )
    assert result.status == "EXECUTED"
    assert result.output == 3


def test_action_runtime_contains_tool_exception():
    registry = ToolRegistry()

    def explode(args):
        raise RuntimeError("boom")

    registry.register(
        ToolDefinition(
            tool_id="text.fail",
            handler=explode,
            required_capabilities=("text_stats",),
        )
    )
    result = ActionRuntime(tools=registry).execute(
        ActionProposal("text.fail"),
        selected_egos=[_ego()],
    )
    assert result.status == "ERROR"
    assert result.error == "RuntimeError: boom"
