from __future__ import annotations

from typing import Any

from .models import EgoManifest


def ego_to_a2a_skill(ego: EgoManifest) -> dict[str, Any]:
    """Export the common discovery subset as an A2A AgentSkill-shaped object."""
    tags = tuple(dict.fromkeys((*ego.tags, *ego.keywords, *ego.provides)))
    return {
        "id": ego.ego_id,
        "name": ego.name,
        "description": ego.description or ego.name,
        "tags": list(tags),
        "examples": list(ego.examples),
    }
