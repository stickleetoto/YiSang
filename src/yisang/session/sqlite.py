from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any

from .models import SessionMessage
from .port import SessionPort


class SQLiteSessionPort(SessionPort):
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_messages (
                    session_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    metadata_json TEXT NOT NULL,
                    PRIMARY KEY (session_id, sequence)
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_session_messages_created
                ON session_messages(session_id, created_at)
                """
            )
            self._conn.commit()

    def append(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> SessionMessage:
        if not session_id.strip():
            raise ValueError("session_id must be non-empty")
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) AS max_sequence
                FROM session_messages
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            sequence = int(row["max_sequence"]) + 1
            message = SessionMessage(
                session_id=session_id,
                sequence=sequence,
                role=role,
                content=content,
                metadata=dict(metadata or {}),
            )
            self._conn.execute(
                """
                INSERT INTO session_messages (
                    session_id, sequence, role, content, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message.session_id,
                    message.sequence,
                    message.role,
                    message.content,
                    message.created_at,
                    json.dumps(message.metadata, ensure_ascii=False, sort_keys=True),
                ),
            )
            self._conn.commit()
            return message

    def history(
        self,
        session_id: str,
        *,
        limit: int | None = None,
    ) -> list[SessionMessage]:
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")
        if limit == 0:
            return []

        with self._lock:
            if limit is None:
                rows = self._conn.execute(
                    """
                    SELECT session_id, sequence, role, content, created_at, metadata_json
                    FROM session_messages
                    WHERE session_id = ?
                    ORDER BY sequence ASC
                    """,
                    (session_id,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT session_id, sequence, role, content, created_at, metadata_json
                    FROM session_messages
                    WHERE session_id = ?
                    ORDER BY sequence DESC
                    LIMIT ?
                    """,
                    (session_id, limit),
                ).fetchall()
                rows = list(reversed(rows))
        return [_row_to_message(row) for row in rows]

    def clear(self, session_id: str) -> int:
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM session_messages WHERE session_id = ?",
                (session_id,),
            )
            self._conn.commit()
            return int(cursor.rowcount)

    def session_ids(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT DISTINCT session_id
                FROM session_messages
                ORDER BY session_id ASC
                """
            ).fetchall()
        return [str(row["session_id"]) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "SQLiteSessionPort":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def _row_to_message(row: sqlite3.Row) -> SessionMessage:
    try:
        metadata = json.loads(row["metadata_json"])
    except json.JSONDecodeError:
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    return SessionMessage(
        session_id=str(row["session_id"]),
        sequence=int(row["sequence"]),
        role=str(row["role"]),
        content=str(row["content"]),
        created_at=float(row["created_at"]),
        metadata=metadata,
    )
