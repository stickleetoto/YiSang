from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from yisang.memory.transfer import build_memory_archive


@dataclass(frozen=True)
class InvarianceSnapshot:
    agent_id: str
    memory_digest: str
    ego_ids: tuple[str, ...]
    state_digest: str


def capture_invariance_snapshot(runtime) -> InvarianceSnapshot:
    memory_archive = build_memory_archive(runtime.memory)
    state = {
        "active_project": runtime.state.active_project,
        "current_goal": runtime.state.current_goal,
        "tags": dict(runtime.state.tags),
    }
    state_digest = hashlib.sha256(
        json.dumps(
            state,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    return InvarianceSnapshot(
        agent_id=runtime.identity.agent_id,
        memory_digest=memory_archive["records_sha256"],
        ego_ids=tuple(
            sorted(ego.ego_id for ego in runtime.ego_registry.list_all())
        ),
        state_digest=state_digest,
    )


def compare_invariance(
    before: InvarianceSnapshot,
    after: InvarianceSnapshot,
) -> dict[str, bool]:
    return {
        "identity_preserved": before.agent_id == after.agent_id,
        "memory_preserved": before.memory_digest == after.memory_digest,
        "capabilities_preserved": before.ego_ids == after.ego_ids,
        "state_preserved": before.state_digest == after.state_digest,
    }
