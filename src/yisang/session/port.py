from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import SessionMessage


class SessionPort(ABC):
    """Replay-oriented conversation state.

    SessionPort is intentionally separate from MemoryPort. Persisting a session
    message never creates durable agent memory; durable memory must still pass
    through MemoryProposal + MemoryGovernor.
    """

    @abstractmethod
    def append(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> SessionMessage:
        raise NotImplementedError

    @abstractmethod
    def history(
        self,
        session_id: str,
        *,
        limit: int | None = None,
    ) -> list[SessionMessage]:
        raise NotImplementedError

    @abstractmethod
    def clear(self, session_id: str) -> int:
        """Delete session messages and return the number removed."""
        raise NotImplementedError

    @abstractmethod
    def session_ids(self) -> list[str]:
        raise NotImplementedError
