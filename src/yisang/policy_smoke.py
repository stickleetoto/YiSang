from __future__ import annotations

import argparse
import json

from yisang.ego.models import EgoManifest, EgoRiskHints
from yisang.execution.gate import ActionGate
from yisang.execution.models import ActionProposal
from yisang.execution.runtime import ActionRuntime
from yisang.execution.tools import ToolDefinition, ToolRegistry
from yisang.policy import AuthorizationPolicyEngine, PolicyRule


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yisang-policy-smoke")
    parser.parse_args(argv)

    tools = ToolRegistry()
    tools.register(
        ToolDefinition(
            tool_id="workspace.read",
            handler=lambda args: f"read:{args['path']}",
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
    ego = EgoManifest(
        ego_id="ego.repo",
        name="Repository Reader",
        provides=("repository_analysis",),
        permissions={"filesystem": "read"},
        schema_version=2,
        version="1.0.0",
        description="Read repository documentation.",
        risk=EgoRiskHints(
            read_only=True,
            destructive=False,
            idempotent=True,
            open_world=False,
        ),
    )
    policy = AuthorizationPolicyEngine(
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
    runtime = ActionRuntime(
        tools=tools,
        gate=ActionGate(policy_engine=policy),
    )

    exposed = runtime.available_tools(selected_egos=[ego])
    allowed = runtime.execute(
        ActionProposal(
            "workspace.read",
            {"path": "docs/EXECUTION.md"},
        ),
        selected_egos=[ego],
    )
    forbidden = runtime.execute(
        ActionProposal(
            "workspace.read",
            {"path": "docs/private/token.txt"},
        ),
        selected_egos=[ego],
    )
    no_permit = runtime.execute(
        ActionProposal(
            "workspace.read",
            {"path": "src/yisang/core/runtime.py"},
        ),
        selected_egos=[ego],
    )

    payload = {
        "ready": bool(
            len(exposed) == 1
            and allowed.status == "EXECUTED"
            and forbidden.status == "DENIED"
            and forbidden.gate_reason == "policy_denied"
            and no_permit.status == "DENIED"
            and no_permit.gate_reason == "policy_no_permit"
        ),
        "tool_exposed_for_partial_scope": len(exposed) == 1,
        "allowed_resource_status": allowed.status,
        "explicit_forbid_status": forbidden.status,
        "explicit_forbid_reason": forbidden.gate_reason,
        "unmatched_resource_status": no_permit.status,
        "unmatched_resource_reason": no_permit.gate_reason,
        "deny_by_default": True,
        "risk_hints_grant_authority": False,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
