from yisang.ego.models import EgoManifest, EgoRiskHints
from yisang.execution.gate import ActionGate
from yisang.execution.models import ActionProposal
from yisang.execution.runtime import ActionRuntime
from yisang.execution.tools import ToolDefinition, ToolRegistry
from yisang.policy import AuthorizationPolicyEngine, PolicyRule


def _registry():
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            tool_id="workspace.read",
            handler=lambda args: args["path"],
            required_capabilities=("repository_analysis",),
            required_permissions={"filesystem": "read"},
            policy_action="filesystem.read",
            resource_type="workspace_path",
            resource_argument="path",
            argument_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        )
    )
    return registry


def _ego():
    return EgoManifest(
        ego_id="ego.repo",
        name="Repository",
        provides=("repository_analysis",),
        permissions={"filesystem": "read"},
        schema_version=2,
        version="1.0.0",
        description="Repository reader",
        risk=EgoRiskHints(
            read_only=True,
            destructive=False,
            idempotent=True,
            open_world=False,
        ),
    )


def _policy():
    return AuthorizationPolicyEngine(
        [
            PolicyRule(
                "permit-docs",
                "permit",
                principal="ego.repo",
                action="filesystem.read",
                resource_type="workspace_path",
                resource="docs/*",
                context_equals={"side_effecting": False},
            ),
            PolicyRule(
                "forbid-private",
                "forbid",
                principal="ego.repo",
                action="filesystem.read",
                resource_type="workspace_path",
                resource="docs/private/*",
            ),
        ]
    )


def test_action_gate_policy_permits_allowed_resource():
    gate = ActionGate(policy_engine=_policy())
    decision = gate.evaluate(
        ActionProposal("workspace.read", {"path": "docs/EXECUTION.md"}),
        selected_egos=[_ego()],
        tools=_registry(),
    )
    assert decision.allowed is True
    assert decision.ego_id == "ego.repo"
    assert decision.policy_reason == "explicit_permit"
    assert decision.policy_rule_ids == ("permit-docs",)


def test_action_gate_policy_explicit_forbid_wins():
    gate = ActionGate(policy_engine=_policy())
    decision = gate.evaluate(
        ActionProposal("workspace.read", {"path": "docs/private/key.txt"}),
        selected_egos=[_ego()],
        tools=_registry(),
    )
    assert decision.allowed is False
    assert decision.reason == "policy_denied"
    assert decision.policy_reason == "explicit_forbid"
    assert decision.policy_rule_ids == ("forbid-private",)


def test_action_gate_policy_no_permit_fails_closed():
    gate = ActionGate(policy_engine=_policy())
    decision = gate.evaluate(
        ActionProposal("workspace.read", {"path": "src/yisang/core/runtime.py"}),
        selected_egos=[_ego()],
        tools=_registry(),
    )
    assert decision.allowed is False
    assert decision.reason == "policy_no_permit"


def test_tool_can_be_exposed_when_some_resource_scope_is_permitted():
    runtime = ActionRuntime(
        tools=_registry(),
        gate=ActionGate(policy_engine=_policy()),
    )
    specs = runtime.available_tools(selected_egos=[_ego()])
    assert [item["tool_id"] for item in specs] == ["workspace.read"]
    assert specs[0]["policy_action"] == "filesystem.read"
    assert specs[0]["resource_argument"] == "path"


def test_execution_rechecks_policy_for_actual_resource():
    runtime = ActionRuntime(
        tools=_registry(),
        gate=ActionGate(policy_engine=_policy()),
    )
    result = runtime.execute(
        ActionProposal("workspace.read", {"path": "src/yisang/core/runtime.py"}),
        selected_egos=[_ego()],
    )
    assert result.status == "DENIED"
    assert result.gate_reason == "policy_no_permit"
