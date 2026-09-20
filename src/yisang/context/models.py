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
    library: list[dict[str, Any]] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    action_history: list[dict[str, Any]] = field(default_factory=list)
    session_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "agent_id": self.agent_id,
            "user_text": self.user_text,
            "identity": self.identity,
            "state": self.state,
            "memories": self.memories,
            "egos": self.egos,
            "library": self.library,
            "constraints": self.constraints,
            "tools": self.tools,
            "action_history": self.action_history,
            "session_history": self.session_history,
        }

    def approx_chars(self) -> int:
        return len(json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True))


@dataclass(frozen=True)
class ContextBudgetReport:
    max_total_chars: int
    total_chars: int
    user_chars: int
    memory_chars: int
    ego_chars: int
    library_chars: int
    tool_chars: int
    action_history_chars: int
    session_chars: int
    selected_memories: int
    dropped_memories: int
    selected_egos: int
    dropped_egos: int
    selected_library_items: int
    dropped_library_items: int
    selected_tools: int
    dropped_tools: int
    selected_action_history: int
    dropped_action_history: int
    selected_session_messages: int
    dropped_session_messages: int
    user_truncated: bool

    @property
    def within_budget(self) -> bool:
        return self.total_chars <= self.max_total_chars


@dataclass(frozen=True)
class CompiledContext:
    pack: ContextPack
    budget: ContextBudgetReport
