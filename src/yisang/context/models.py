from dataclasses import dataclass, field
from typing import Any

@dataclass
class ContextPack:
    request_id: str
    agent_id: str
    user_text: str
    identity: dict[str, Any]
    state: dict[str, Any]
    memories: list[dict[str, Any]]
    egos: list[dict[str, Any]]
    constraints: list[str] = field(default_factory=list)
