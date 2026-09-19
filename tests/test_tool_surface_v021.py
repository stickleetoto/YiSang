from pathlib import Path

from yisang.ego.models import EgoManifest
from yisang.execution.builtin import register_workspace_read_tools
from yisang.execution.gate import ActionGate
from yisang.execution.models import ActionProposal
from yisang.execution.runtime import ActionRuntime
from yisang.execution.tools import ToolDefinition, ToolRegistry


def _repo_ego():
    return EgoManifest(
        ego_id="ego.repo",
        name="Repository Inspector",
        provides=("repository_analysis",),
        permissions={"filesystem": "read"},
    )


def test_tool_surface_contains_only_authorized_tools():
    tools = ToolRegistry()
    tools.register(
        ToolDefinition(
            tool_id="repo.read",
            handler=lambda args: "ok",
            required_capabilities=("repository_analysis",),
            required_permissions={"filesystem": "read"},
        )
    )
    tools.register(
        ToolDefinition(
            tool_id="repo.write",
            handler=lambda args: "ok",
            required_capabilities=("repository_analysis",),
            required_permissions={"filesystem": "workspace"},
            side_effecting=True,
        )
    )

    runtime = ActionRuntime(tools=tools, gate=ActionGate())
    surfaced = runtime.available_tools(selected_egos=[_repo_ego()])

    assert [item["tool_id"] for item in surfaced] == ["repo.read"]
    assert surfaced[0]["authorized_by_ego"] == "ego.repo"


def test_argument_schema_is_checked_before_handler_runs():
    called = []

    tools = ToolRegistry()
    tools.register(
        ToolDefinition(
            tool_id="repo.read",
            handler=lambda args: called.append(args) or "ok",
            required_capabilities=("repository_analysis",),
            required_permissions={"filesystem": "read"},
            argument_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        )
    )

    result = ActionRuntime(tools=tools).execute(
        ActionProposal("repo.read", {"path": "README.md", "extra": 1}),
        selected_egos=[_repo_ego()],
    )

    assert result.status == "ERROR"
    assert "unknown arguments" in (result.error or "")
    assert called == []


def test_builtin_workspace_tools_are_read_only_and_path_confined(tmp_path: Path):
    (tmp_path / "README.md").write_text("hello", encoding="utf-8")
    (tmp_path / "src").mkdir()

    tools = ToolRegistry()
    register_workspace_read_tools(tools, root=tmp_path)
    runtime = ActionRuntime(tools=tools)

    listed = runtime.execute(
        ActionProposal("workspace.list", {}),
        selected_egos=[_repo_ego()],
    )
    assert listed.status == "EXECUTED"
    assert {item["path"] for item in listed.output} == {"README.md", "src"}

    read = runtime.execute(
        ActionProposal("workspace.read_text", {"path": "README.md"}),
        selected_egos=[_repo_ego()],
    )
    assert read.status == "EXECUTED"
    assert read.output == "hello"

    outside = tmp_path.parent / "yisang-outside-test.txt"
    outside.write_text("secret", encoding="utf-8")
    try:
        escaped = runtime.execute(
            ActionProposal(
                "workspace.read_text",
                {"path": "../yisang-outside-test.txt"},
            ),
            selected_egos=[_repo_ego()],
        )
        assert escaped.status == "ERROR"
        assert "PermissionError" in (escaped.error or "")
    finally:
        outside.unlink(missing_ok=True)
