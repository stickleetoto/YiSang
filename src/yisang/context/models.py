from dataclasses import dataclass, field
from typing import Any
import json


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
    tools: list[dict[str, Any]] = field(default_factory=list)
    action_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "agent_id": self.agent_id,
            "user_text": self.user_text,
            "identity": self.identity,
            "state": self.state,
            "memories": self.memories,
            "egos": self.egos,
            "constraints": self.constraints,
            "tools": self.tools,
            "action_history": self.action_history,
        }

    def approx_chars(self) -> int:
        return len(json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True))
