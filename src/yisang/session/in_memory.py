from __future__ import annotations

from collections import defaultdict
from threading import RLock
from typing import Any

from .models import SessionMessage
from .port import SessionPort


class InMemorySessionPort(SessionPort):
    def __init__(self) -> None:
        self._lock = RLock()
        self._messages: dict[str, list[SessionMessage]] = defaultdict(list)

    def append(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> SessionMessage:
        with self._lock:
            message = SessionMessage(
                session_id=session_id,
                sequence=len(self._messages[session_id]) + 1,
                role=role,
                content=content,
                metadata=dict(metadata or {}),
            )
            self._messages[session_id].append(message)
            return message

    def history(
        self,
        session_id: str,
        *,
        limit: int | None = None,
    ) -> list[SessionMessage]:
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")
        with self._lock:
            items = list(self._messages.get(session_id, ()))
        if limit is None:
            return items
        if limit == 0:
            return []
        return items[-limit:]

    def clear(self, session_id: str) -> int:
        with self._lock:
            items = self._messages.pop(session_id, [])
            return len(items)

    def session_ids(self) -> list[str]:
        with self._lock:
            return sorted(
                session_id
                for session_id, items in self._messages.items()
                if items
            )
