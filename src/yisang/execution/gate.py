from __future__ import annotations

from yisang.ego.models import EgoManifest

from .models import ActionDecision, ActionProposal
from .tools import ToolRegistry

_FILESYSTEM_LEVELS = {
    "none": 0,
    "read": 1,
    "workspace": 2,
    "unrestricted": 3,
}


class ActionGate:
    """Authorize model-proposed actions against selected E.G.O capabilities."""

    def __init__(self, *, allow_side_effects: bool = False) -> None:
        self.allow_side_effects = allow_side_effects

    def evaluate(
        self,
        proposal: ActionProposal,
        *,
        selected_egos: list[EgoManifest],
        tools: ToolRegistry,
    ) -> ActionDecision:
        if not tools.has(proposal.action):
            return ActionDecision(proposal.action, False, "unknown_tool")

        tool = tools.get(proposal.action)
        if tool.side_effecting and not self.allow_side_effects:
            return ActionDecision(proposal.action, False, "side_effects_disabled")

        required = set(tool.required_capabilities)
        candidates = [
            ego for ego in selected_egos if required.issubset(set(ego.provides))
        ]
        if not candidates:
            return ActionDecision(proposal.action, False, "missing_capability")

        for ego in candidates:
            if _permissions_allow(ego.permissions, tool.required_permissions):
                return ActionDecision(
                    proposal.action,
                    True,
                    "allowed",
                    ego_id=ego.ego_id,
                )

        return ActionDecision(proposal.action, False, "insufficient_permission")


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
