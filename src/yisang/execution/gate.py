from __future__ import annotations

from yisang.ego.models import EgoManifest
from yisang.policy import (
    AuthorizationPolicyEngine,
    AuthorizationRequest,
    PolicyPrincipal,
    PolicyResource,
)

from .models import ActionDecision, ActionProposal
from .tools import ToolDefinition, ToolRegistry

_FILESYSTEM_LEVELS = {
    "none": 0,
    "read": 1,
    "workspace": 2,
    "unrestricted": 3,
}


class ActionGate:
    """Authorize model-proposed actions against capability and policy."""

    def __init__(
        self,
        *,
        allow_side_effects: bool = False,
        policy_engine: AuthorizationPolicyEngine | None = None,
    ) -> None:
        self.allow_side_effects = allow_side_effects
        self.policy_engine = policy_engine

    def evaluate(
        self,
        proposal: ActionProposal,
        *,
        selected_egos: list[EgoManifest],
        tools: ToolRegistry,
        exposure_only: bool = False,
    ) -> ActionDecision:
        if not tools.has(proposal.action):
            return ActionDecision(proposal.action, False, "unknown_tool")

        tool = tools.get(proposal.action)
        if tool.side_effecting and not self.allow_side_effects:
            return ActionDecision(
                proposal.action,
                False,
                "side_effects_disabled",
            )

        required = set(tool.required_capabilities)
        candidates = [
            ego
            for ego in selected_egos
            if required.issubset(set(ego.provides))
        ]
        if not candidates:
            return ActionDecision(
                proposal.action,
                False,
                "missing_capability",
            )

        permission_candidates = [
            ego
            for ego in candidates
            if _permissions_allow(
                ego.permissions,
                tool.required_permissions,
            )
        ]
        if not permission_candidates:
            return ActionDecision(
                proposal.action,
                False,
                "insufficient_permission",
            )

        if self.policy_engine is None:
            ego = permission_candidates[0]
            return ActionDecision(
                proposal.action,
                True,
                "allowed",
                ego_id=ego.ego_id,
            )

        last_reason = "policy_no_permit"
        matched_rule_ids: tuple[str, ...] = ()
        for ego in permission_candidates:
            policy = self.policy_engine.evaluate(
                _policy_request(
                    proposal,
                    tool=tool,
                    ego=ego,
                    exposure_only=exposure_only,
                ),
                exposure_only=exposure_only,
            )
            if policy.allowed:
                return ActionDecision(
                    proposal.action,
                    True,
                    "allowed",
                    ego_id=ego.ego_id,
                    policy_reason=policy.reason,
                    policy_rule_ids=policy.matched_rule_ids,
                )
            if policy.reason == "explicit_forbid":
                last_reason = "policy_denied"
                matched_rule_ids = policy.matched_rule_ids

        return ActionDecision(
            proposal.action,
            False,
            last_reason,
            policy_reason=(
                "explicit_forbid"
                if last_reason == "policy_denied"
                else "no_matching_permit"
            ),
            policy_rule_ids=matched_rule_ids,
        )


def _policy_request(
    proposal: ActionProposal,
    *,
    tool: ToolDefinition,
    ego: EgoManifest,
    exposure_only: bool,
) -> AuthorizationRequest:
    resource_id = tool.tool_id
    if tool.resource_argument is not None:
        value = proposal.arguments.get(tool.resource_argument)
        if value is not None:
            resource_id = str(value)
        elif exposure_only:
            resource_id = "*"

    risk = ego.risk
    return AuthorizationRequest(
        principal=PolicyPrincipal(
            principal_type="ego",
            principal_id=ego.ego_id,
            version=getattr(ego, "version", None),
        ),
        action=tool.policy_action or tool.tool_id,
        resource=PolicyResource(
            resource_type=tool.resource_type,
            resource_id=resource_id,
            attributes={"tool_id": tool.tool_id},
        ),
        context={
            "tool_id": tool.tool_id,
            "requested_by": proposal.requested_by,
            "side_effecting": tool.side_effecting,
            "ego_runtime_type": getattr(ego, "runtime_type", "prompt"),
            "risk_read_only": risk.read_only,
            "risk_destructive": risk.destructive,
            "risk_idempotent": risk.idempotent,
            "risk_open_world": risk.open_world,
        },
    )


def _permissions_allow(
    granted: dict[str, str | bool],
    required: dict[str, str | bool],
) -> bool:
    for key, needed in required.items():
        have = granted.get(key)

        if isinstance(needed, bool):
            if needed and have is not True:
                return False
            continue

        if key == "filesystem":
            have_level = _FILESYSTEM_LEVELS.get(str(have), -1)
            need_level = _FILESYSTEM_LEVELS.get(str(needed), 10)
            if have_level < need_level:
                return False
            continue

        if have != needed:
            return False

    return True
