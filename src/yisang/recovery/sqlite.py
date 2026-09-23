from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any
import uuid

from .models import (
    RUN_EVENT_TYPES,
    RecoveryCheckpoint,
    RunJournalEvent,
    SideEffectReceipt,
)
from .port import CheckpointPort, RunJournalPort, SideEffectReceiptPort


class SQLiteRecoveryStore(
    RunJournalPort,
    CheckpointPort,
    SideEffectReceiptPort,
):
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
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS side_effect_receipts (
                    receipt_id TEXT PRIMARY KEY,
                    goal_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    tool_id TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    state TEXT NOT NULL,
                    result_ref TEXT,
                    evidence_refs_json TEXT NOT NULL,
                    failure_reason TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    UNIQUE(goal_id, idempotency_key)
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_side_effect_goal
                ON side_effect_receipts(goal_id, created_at)
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
                    ORDER BY created_at DESC, journal_sequence DESC
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

    def reserve(
        self,
        *,
        goal_id: str,
        run_id: str,
        idempotency_key: str,
        tool_id: str,
        request_digest: str,
        metadata: dict[str, Any] | None = None,
    ) -> SideEffectReceipt:
        if not goal_id.strip() or not run_id.strip():
            raise ValueError("goal_id and run_id must be non-empty")
        if not idempotency_key.strip():
            raise ValueError("idempotency_key must be non-empty")
        with self._lock:
            existing = self._conn.execute(
                """
                SELECT * FROM side_effect_receipts
                WHERE goal_id=? AND idempotency_key=?
                """,
                (goal_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                receipt = _receipt_from_row(existing)
                if (
                    receipt.request_digest != request_digest
                    or receipt.tool_id != tool_id
                ):
                    raise ValueError(
                        "idempotency key reused for different side effect"
                    )
                return receipt

            receipt = SideEffectReceipt(
                receipt_id=f"side-effect-{uuid.uuid4().hex[:16]}",
                goal_id=goal_id,
                run_id=run_id,
                idempotency_key=idempotency_key,
                tool_id=tool_id,
                request_digest=request_digest,
                metadata=dict(metadata or {}),
            )
            self._conn.execute(
                """
                INSERT INTO side_effect_receipts (
                    receipt_id, goal_id, run_id, idempotency_key,
                    tool_id, request_digest, state, result_ref,
                    evidence_refs_json, failure_reason, metadata_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _receipt_values(receipt),
            )
            self._conn.commit()
        return receipt

    def get_receipt(
        self,
        goal_id: str,
        idempotency_key: str,
    ) -> SideEffectReceipt | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM side_effect_receipts
                WHERE goal_id=? AND idempotency_key=?
                """,
                (goal_id, idempotency_key),
            ).fetchone()
        return None if row is None else _receipt_from_row(row)

    def commit_receipt(
        self,
        receipt_id: str,
        *,
        result_ref: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> SideEffectReceipt:
        current = self._receipt_by_id(receipt_id)
        if current.state == "committed":
            return current
        if current.state == "failed":
            raise ValueError("failed receipt cannot become committed")
        value = result_ref.strip()
        if not value:
            raise ValueError("result_ref must be non-empty")
        with self._lock:
            self._conn.execute(
                """
                UPDATE side_effect_receipts
                SET state='committed', result_ref=?,
                    evidence_refs_json=?, updated_at=?
                WHERE receipt_id=?
                """,
                (
                    value,
                    json.dumps(evidence_refs, ensure_ascii=False),
                    __import__("time").time(),
                    receipt_id,
                ),
            )
            self._conn.commit()
        return self._receipt_by_id(receipt_id)

    def fail_receipt(
        self,
        receipt_id: str,
        *,
        reason: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> SideEffectReceipt:
        current = self._receipt_by_id(receipt_id)
        if current.state == "committed":
            raise ValueError("committed receipt cannot become failed")
        if current.state == "failed":
            return current
        value = reason.strip()
        if not value:
            raise ValueError("reason must be non-empty")
        with self._lock:
            self._conn.execute(
                """
                UPDATE side_effect_receipts
                SET state='failed', failure_reason=?,
                    evidence_refs_json=?, updated_at=?
                WHERE receipt_id=?
                """,
                (
                    value,
                    json.dumps(evidence_refs, ensure_ascii=False),
                    __import__("time").time(),
                    receipt_id,
                ),
            )
            self._conn.commit()
        return self._receipt_by_id(receipt_id)

    def receipts(
        self,
        goal_id: str,
    ) -> tuple[SideEffectReceipt, ...]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM side_effect_receipts
                WHERE goal_id=?
                ORDER BY created_at, receipt_id
                """,
                (goal_id,),
            ).fetchall()
        return tuple(_receipt_from_row(row) for row in rows)

    def _receipt_by_id(self, receipt_id: str) -> SideEffectReceipt:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM side_effect_receipts
                WHERE receipt_id=?
                """,
                (receipt_id,),
            ).fetchone()
        if row is None:
            raise KeyError(receipt_id)
        return _receipt_from_row(row)

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



def _receipt_values(receipt: SideEffectReceipt) -> tuple[object, ...]:
    return (
        receipt.receipt_id,
        receipt.goal_id,
        receipt.run_id,
        receipt.idempotency_key,
        receipt.tool_id,
        receipt.request_digest,
        receipt.state,
        receipt.result_ref,
        json.dumps(receipt.evidence_refs, ensure_ascii=False),
        receipt.failure_reason,
        json.dumps(receipt.metadata, ensure_ascii=False, sort_keys=True),
        receipt.created_at,
        receipt.updated_at,
    )


def _receipt_from_row(row: sqlite3.Row) -> SideEffectReceipt:
    metadata = json.loads(row["metadata_json"])
    return SideEffectReceipt(
        receipt_id=row["receipt_id"],
        goal_id=row["goal_id"],
        run_id=row["run_id"],
        idempotency_key=row["idempotency_key"],
        tool_id=row["tool_id"],
        request_digest=row["request_digest"],
        state=row["state"],
        result_ref=row["result_ref"],
        evidence_refs=tuple(json.loads(row["evidence_refs_json"])),
        failure_reason=row["failure_reason"],
        metadata=metadata if isinstance(metadata, dict) else {},
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
    )
