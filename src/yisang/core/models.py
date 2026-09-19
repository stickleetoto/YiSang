from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class YiSangRequest:
    request_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class YiSangResponse:
    request_id: str
    text: str
    engine_id: str
    verification_status: str
    used_memory_ids: list[str] = field(default_factory=list)
    used_ego_ids: list[str] = field(default_factory=list)
    action_results: list[dict[str, Any]] = field(default_factory=list)
