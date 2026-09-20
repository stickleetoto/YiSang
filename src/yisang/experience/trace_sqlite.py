from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from threading import RLock

from .trace import ActionTrace, ReplayExecutionTemplate
from .trace_port import ActionTracePort


class SQLiteActionTracePort(ActionTracePort):
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
                CREATE TABLE IF NOT EXISTS experience_action_traces (
                    trace_id TEXT PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    tool_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    goal_satisfied INTEGER NOT NULL,
                    arguments_sha256 TEXT NOT NULL,
                    replay_template_json TEXT,
                    manifest_rejection_reason TEXT,
                    created_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_experience_action_traces_request
                ON experience_action_traces(request_id, ordinal)
                """
            )
            self._conn.commit()

    def put_trace(self, trace: ActionTrace) -> None:
        template_json = (
            json.dumps(
                trace.replay_template.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
            )
            if trace.replay_template is not None
            else None
        )
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO experience_action_traces (
                        trace_id, request_id, ordinal, tool_id, status,
                        goal_satisfied, arguments_sha256, replay_template_json,
                        manifest_rejection_reason, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trace.trace_id,
                        trace.request_id,
                        trace.ordinal,
                        trace.tool_id,
                        trace.status,
                        int(trace.goal_satisfied),
                        trace.arguments_sha256,
                        template_json,
                        trace.manifest_rejection_reason,
                        trace.created_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    f"duplicate action trace: {trace.trace_id}"
                ) from exc
            self._conn.commit()

    def get_trace(self, trace_id: str) -> ActionTrace | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM experience_action_traces WHERE trace_id = ?",
                (trace_id,),
            ).fetchone()
        return None if row is None else _from_row(row)

    def for_request(self, request_id: str) -> tuple[ActionTrace, ...]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM experience_action_traces
                WHERE request_id = ?
                ORDER BY ordinal, trace_id
                """,
                (request_id,),
            ).fetchall()
        return tuple(_from_row(row) for row in rows)

    def all_traces(self) -> tuple[ActionTrace, ...]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM experience_action_traces
                ORDER BY request_id, ordinal, trace_id
                """
            ).fetchall()
        return tuple(_from_row(row) for row in rows)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "SQLiteActionTracePort":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def _from_row(row: sqlite3.Row) -> ActionTrace:
    template = (
        ReplayExecutionTemplate.from_dict(
            json.loads(row["replay_template_json"])
        )
        if row["replay_template_json"] is not None
        else None
    )
    return ActionTrace(
        trace_id=row["trace_id"],
        request_id=row["request_id"],
        ordinal=int(row["ordinal"]),
        tool_id=row["tool_id"],
        status=row["status"],
        goal_satisfied=bool(row["goal_satisfied"]),
        arguments_sha256=row["arguments_sha256"],
        replay_template=template,
        manifest_rejection_reason=row["manifest_rejection_reason"],
        created_at=float(row["created_at"]),
    )
