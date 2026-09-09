from dataclasses import dataclass, field

@dataclass(frozen=True)
class IdentityCharter:
    agent_id: str
    name: str
    principles: tuple[str, ...] = (
        "preserve_continuity",
        "evidence_before_memory",
        "verify_before_commit",
    )

@dataclass
class AgentState:
    active_engine: str
    active_project: str | None = None
    current_goal: str | None = None
    tags: dict[str, str] = field(default_factory=dict)
