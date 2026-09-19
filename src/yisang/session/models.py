from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import time


@dataclass(frozen=True)
class SessionMessage:
    session_id: str
    sequence: int
    role: str
    content: str
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id must be non-empty")
        if self.sequence <= 0:
            raise ValueError("sequence must be positive")
        if self.role not in {"system", "developer", "user", "assistant", "tool"}:
            raise ValueError(f"unsupported session role: {self.role}")
        if not isinstance(self.content, str):
            raise ValueError("content must be a string")
