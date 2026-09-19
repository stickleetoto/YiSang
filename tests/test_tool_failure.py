import pytest

from yisang.ego.models import EgoManifest
from yisang.execution.failure import (
    ToolFailureCategory,
    failure_from_exception,
    failure_from_gate_reason,
)
from yisang.execution.models import ActionProposal
from yisang.execution.runtime import ActionRuntime
from yisang.execution.tools import ToolDefinition, ToolRegistry


def test_gate_failure_is_structured():
    failure = failure_from_gate_reason("unknown_tool", tool_id="missing.tool")

    assert failure.category is ToolFailureCategory.INVALID_ARGUMENTS
    assert failure.retryable is True
    assert failure.blame == "model"
    assert failure.evidence["tool_id"] == "missing.tool"


@pytest.mark.parametrize(
    ("exc", "category", "retryable"),
    [
        (TimeoutError("slow"), ToolFailureCategory.TIMEOUT, True),
        (ConnectionError("down"), ToolFailureCategory.TRANSIENT, True),
        (PermissionError("denied"), ToolFailureCategory.PERMISSION, False),
        (FileNotFoundError("missing"), ToolFailureCategory.ENVIRONMENT, True),
        (ValueError("bad arg"), ToolFailureCategory.INVALID_ARGUMENTS, True),
        (RuntimeError("boom"), ToolFailureCategory.EXECUTION, False),
    ],
)
def test_exception_failure_classification(exc, category, retryable):
    failure = failure_from_exception(exc, tool_id="tool")

    assert failure.category is category
    assert failure.retryable is retryable
    assert failure.evidence["exception_type"] == type(exc).__name__


def test_action_runtime_attaches_failure_for_invalid_arguments():
    tools = ToolRegistry()
    tools.register(
        ToolDefinition(
            tool_id="text.length",
            handler=lambda args: len(args["text"]),
            required_capabilities=("text_stats",),
            argument_schema={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
        )
    )
    runtime = ActionRuntime(tools=tools)
    ego = EgoManifest(
        ego_id="ego.text",
        name="Text",
        provides=("text_stats",),
        keywords=("text",),
    )

    result = runtime.execute(
        ActionProposal("text.length", {}),
        selected_egos=[ego],
    )

    assert result.status == "ERROR"
    assert result.failure is not None
    assert result.failure.category is ToolFailureCategory.INVALID_ARGUMENTS
    assert result.to_dict()["failure"]["category"] == "invalid_arguments"


def test_action_runtime_attaches_failure_for_permission_denial():
    tools = ToolRegistry()
    tools.register(
        ToolDefinition(
            tool_id="workspace.write",
            handler=lambda args: None,
            required_capabilities=("repo_write",),
            required_permissions={"filesystem": "workspace"},
            side_effecting=True,
        )
    )
    runtime = ActionRuntime(tools=tools)
    ego = EgoManifest(
        ego_id="ego.repo",
        name="Repo",
        provides=("repo_write",),
        keywords=("repo",),
        permissions={"filesystem": "workspace"},
    )

    result = runtime.execute(
        ActionProposal("workspace.write", {}),
        selected_egos=[ego],
    )

    assert result.status == "DENIED"
    assert result.failure is not None
    assert result.failure.category is ToolFailureCategory.PERMISSION
    assert result.failure.blame == "policy"
