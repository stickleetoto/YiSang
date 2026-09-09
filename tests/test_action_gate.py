from yisang.ego.models import EgoManifest
from yisang.execution.gate import ActionGate
from yisang.execution.models import ActionProposal
from yisang.execution.tools import ToolDefinition, ToolRegistry


def _registry(*, side_effecting=False, permission="read"):
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            tool_id="repo.inspect",
            handler=lambda args: {"path": args.get("path", ".")},
            required_capabilities=("repository_analysis",),
            required_permissions={"filesystem": permission},
            side_effecting=side_effecting,
        )
    )
    return registry


def _ego(*, permission="read"):
    return EgoManifest(
        ego_id="ego.repo.inspect",
        name="Repository Inspector",
        provides=("repository_analysis",),
        permissions={"filesystem": permission},
    )


def test_gate_allows_matching_ego_and_permission():
    decision = ActionGate().evaluate(
        ActionProposal("repo.inspect", {"path": "."}),
        selected_egos=[_ego()],
        tools=_registry(),
    )
    assert decision.allowed
    assert decision.ego_id == "ego.repo.inspect"


def test_gate_denies_unknown_tool():
    decision = ActionGate().evaluate(
        ActionProposal("missing.tool"),
        selected_egos=[_ego()],
        tools=_registry(),
    )
    assert not decision.allowed
    assert decision.reason == "unknown_tool"


def test_gate_denies_missing_capability():
    wrong = EgoManifest(
        ego_id="ego.other",
        name="Other",
        provides=("something_else",),
        permissions={"filesystem": "unrestricted"},
    )
    decision = ActionGate().evaluate(
        ActionProposal("repo.inspect"),
        selected_egos=[wrong],
        tools=_registry(),
    )
    assert decision.reason == "missing_capability"


def test_gate_denies_insufficient_permission():
    decision = ActionGate().evaluate(
        ActionProposal("repo.inspect"),
        selected_egos=[_ego(permission="read")],
        tools=_registry(permission="workspace"),
    )
    assert decision.reason == "insufficient_permission"


def test_side_effecting_tools_are_disabled_by_default():
    decision = ActionGate().evaluate(
        ActionProposal("repo.inspect"),
        selected_egos=[_ego()],
        tools=_registry(side_effecting=True),
    )
    assert decision.reason == "side_effects_disabled"
