from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

@dataclass(frozen=True)
class InvarianceSnapshot:
    agent_id: str
    memory_digest: str
    ego_ids: tuple[str, ...]

def capture_invariance_snapshot(runtime) -> InvarianceSnapshot:
    memories = [
        {
            "kind": record.kind,
            "content": record.content,
            "source": record.source,
            "confidence": record.confidence,
        }
        for record in runtime.memory.all()
    ]
    encoded = json.dumps(
        memories,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return InvarianceSnapshot(
        agent_id=runtime.identity.agent_id,
        memory_digest=hashlib.sha256(encoded).hexdigest(),
        ego_ids=tuple(sorted(ego.ego_id for ego in runtime.ego_registry.list_all())),
    )

def compare_invariance(before: InvarianceSnapshot, after: InvarianceSnapshot) -> dict[str, bool]:
    return {
        "identity_preserved": before.agent_id == after.agent_id,
        "memory_preserved": before.memory_digest == after.memory_digest,
        "capabilities_preserved": before.ego_ids == after.ego_ids,
    }
