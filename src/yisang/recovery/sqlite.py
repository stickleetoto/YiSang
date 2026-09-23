from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any
import uuid

from .models import RUN_EVENT_TYPES, RecoveryCheckpoint, RunJournalEvent
from .port import CheckpointPort, RunJournalPort


class SQLiteRecoveryStore(RunJournalPort, CheckpointPort):
    """SQLite-backed append-only run journal and checkpoint store."""

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
                CREATE TABLE IF NOT EXISTS run_journal (
                    event_id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE(goal_id, run_id, sequence)
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_run_journal_goal_run
                ON run_journal(goal_id, run_id, sequence)
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS recovery_checkpoints (
                    checkpoint_id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    journal_sequence INTEGER NOT NULL,
                    goal_state TEXT NOT NULL,
                    next_action TEXT,
                    completed_action_refs_json TEXT NOT NULL,
                    blockers_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_recovery_checkpoint_goal
                ON recovery_checkpoints(
                    goal_id, run_id, journal_sequence, created_at
                )
                """
            )
            self._conn.commit()

    def append(
        self,
        goal_id: str,
        run_id: str,
        event_type: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> RunJournalEvent:
        if event_type not in RUN_EVENT_TYPES:
            raise ValueError(f"unsupported run journal event: {event_type}")
        if not goal_id.strip():
            raise ValueError("goal_id must be non-empty")
        if not run_id.strip():
            raise ValueError("run_id must be non-empty")
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            row = self._conn.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) AS max_sequence
                FROM run_journal
                WHERE goal_id=? AND run_id=?
                """,
                (goal_id, run_id),
            ).fetchone()
            sequence = int(row["max_sequence"]) + 1
            event = RunJournalEvent(
                event_id=f"run-event-{uuid.uuid4().hex[:16]}",
                goal_id=goal_id,
                run_id=run_id,
                sequence=sequence,
                event_type=event_type,
                payload=dict(payload or {}),
            )
            self._conn.execute(
                """
                INSERT INTO run_journal (
                    event_id, goal_id, run_id, sequence,
                    event_type, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.goal_id,
                    event.run_id,
                    event.sequence,
                    event.event_type,
                    json.dumps(
                        event.payload,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    event.created_at,
                ),
            )
            self._conn.commit()
        return event

    def events(
        self,
        goal_id: str,
        *,
        run_id: str | None = None,
        after_sequence: int = 0,
    ) -> tuple[RunJournalEvent, ...]:
        if after_sequence < 0:
            raise ValueError("after_sequence must be non-negative")
        with self._lock:
            if run_id is None:
                rows = self._conn.execute(
                    """
                    SELECT * FROM run_journal
                    WHERE goal_id=? AND sequence>?
                    ORDER BY created_at, run_id, sequence
                    """,
                    (goal_id, after_sequence),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT * FROM run_journal
                    WHERE goal_id=? AND run_id=? AND sequence>?
                    ORDER BY sequence
                    """,
                    (goal_id, run_id, after_sequence),
                ).fetchall()
        return tuple(_event_from_row(row) for row in rows)

    def latest_sequence(self, goal_id: str, run_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) AS max_sequence
                FROM run_journal
                WHERE goal_id=? AND run_id=?
                """,
                (goal_id, run_id),
            ).fetchone()
        return int(row["max_sequence"])

    def put(self, checkpoint: RecoveryCheckpoint) -> None:
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO recovery_checkpoints (
                        checkpoint_id, goal_id, run_id, journal_sequence,
                        goal_state, next_action, completed_action_refs_json,
                        blockers_json, metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        checkpoint.checkpoint_id,
                        checkpoint.goal_id,
                        checkpoint.run_id,
                        checkpoint.journal_sequence,
                        checkpoint.goal_state,
                        checkpoint.next_action,
                        json.dumps(
                            checkpoint.completed_action_refs,
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            checkpoint.blockers,
                            ensure_ascii=False,
                        ),
                        json.dumps(
                            checkpoint.metadata,
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        checkpoint.created_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    f"duplicate checkpoint: {checkpoint.checkpoint_id}"
                ) from exc
            self._conn.commit()

    def latest(
        self,
        goal_id: str,
        *,
        run_id: str | None = None,
    ) -> RecoveryCheckpoint | None:
        with self._lock:
            if run_id is None:
                row = self._conn.execute(
                    """
                    SELECT * FROM recovery_checkpoints
                    WHERE goal_id=?
                    ORDER BY journal_sequence DESC, created_at DESC
                    LIMIT 1
                    """,
                    (goal_id,),
                ).fetchone()
            else:
                row = self._conn.execute(
                    """
                    SELECT * FROM recovery_checkpoints
                    WHERE goal_id=? AND run_id=?
                    ORDER BY journal_sequence DESC, created_at DESC
                    LIMIT 1
                    """,
                    (goal_id, run_id),
                ).fetchone()
        return None if row is None else _checkpoint_from_row(row)

    def list_all(
        self,
        goal_id: str,
    ) -> tuple[RecoveryCheckpoint, ...]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM recovery_checkpoints
                WHERE goal_id=?
                ORDER BY created_at, journal_sequence, checkpoint_id
                """,
                (goal_id,),
            ).fetchall()
        return tuple(_checkpoint_from_row(row) for row in rows)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "SQLiteRecoveryStore":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def _event_from_row(row: sqlite3.Row) -> RunJournalEvent:
    payload = json.loads(row["payload_json"])
    return RunJournalEvent(
        event_id=row["event_id"],
        goal_id=row["goal_id"],
        run_id=row["run_id"],
        sequence=int(row["sequence"]),
        event_type=row["event_type"],
        payload=payload if isinstance(payload, dict) else {},
        created_at=float(row["created_at"]),
    )


def _checkpoint_from_row(row: sqlite3.Row) -> RecoveryCheckpoint:
    metadata = json.loads(row["metadata_json"])
    return RecoveryCheckpoint(
        checkpoint_id=row["checkpoint_id"],
        goal_id=row["goal_id"],
        run_id=row["run_id"],
        journal_sequence=int(row["journal_sequence"]),
        goal_state=row["goal_state"],
        next_action=row["next_action"],
        completed_action_refs=tuple(
            json.loads(row["completed_action_refs_json"])
        ),
        blockers=tuple(json.loads(row["blockers_json"])),
        metadata=metadata if isinstance(metadata, dict) else {},
        created_at=float(row["created_at"]),
    )
