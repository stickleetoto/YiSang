from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from threading import RLock

from .models import PromotionApplyReceipt, PromotionArtifact
from .port import PromotionPort


class SQLitePromotionPort(PromotionPort):
    """Durable authoritative PromotionPort.

    Promotion artifacts and application receipts are stored separately so
    validation history is not lost when an artifact is later invalidated.
    """

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
                CREATE TABLE IF NOT EXISTS promotion_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    target TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    version TEXT NOT NULL,
                    source_episode_ids_json TEXT NOT NULL,
                    evidence_refs_json TEXT NOT NULL,
                    validation_run_id TEXT NOT NULL,
                    trigger_conditions_json TEXT NOT NULL DEFAULT '[]',
                    scope TEXT NOT NULL DEFAULT 'general',
                    risk_class TEXT NOT NULL DEFAULT 'normal',
                    created_at REAL NOT NULL,
                    state TEXT NOT NULL,
                    invalidated_at REAL,
                    invalidation_reason TEXT,
                    schema_version INTEGER NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS promotion_apply_receipts (
                    apply_id TEXT PRIMARY KEY,
                    artifact_id TEXT NOT NULL,
                    target TEXT NOT NULL,
                    target_ref TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    approval_ref TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_ref TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_promotion_receipts_artifact
                ON promotion_apply_receipts(artifact_id, created_at)
                """
            )
            self._conn.commit()

    def put(self, artifact: PromotionArtifact) -> None:
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO promotion_artifacts (
                        artifact_id, candidate_id, kind, target, title, content,
                        version, source_episode_ids_json, evidence_refs_json,
                        validation_run_id, trigger_conditions_json, scope,
                        risk_class, created_at, state, invalidated_at,
                        invalidation_reason, schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    _artifact_values(artifact),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    f"duplicate promotion artifact: {artifact.artifact_id}"
                ) from exc
            self._conn.commit()

    def get(self, artifact_id: str) -> PromotionArtifact | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM promotion_artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
        return None if row is None else _artifact_from_row(row)

    def list_all(self) -> tuple[PromotionArtifact, ...]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM promotion_artifacts ORDER BY artifact_id"
            ).fetchall()
        return tuple(_artifact_from_row(row) for row in rows)

    def invalidate(self, artifact_id: str, *, reason: str) -> PromotionArtifact:
        artifact = self.get(artifact_id)
        if artifact is None:
            raise KeyError(artifact_id)
        artifact.invalidate(reason)
        with self._lock:
            self._conn.execute(
                """
                UPDATE promotion_artifacts
                SET state = ?, invalidated_at = ?, invalidation_reason = ?
                WHERE artifact_id = ?
                """,
                (
                    artifact.state,
                    artifact.invalidated_at,
                    artifact.invalidation_reason,
                    artifact.artifact_id,
                ),
            )
            self._conn.commit()
        return artifact

    def record_receipt(self, receipt: PromotionApplyReceipt) -> None:
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO promotion_apply_receipts (
                        apply_id, artifact_id, target, target_ref, actor,
                        approval_ref, reason, status, result_ref, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        receipt.apply_id,
                        receipt.artifact_id,
                        receipt.target,
                        receipt.target_ref,
                        receipt.actor,
                        receipt.approval_ref,
                        receipt.reason,
                        receipt.status,
                        receipt.result_ref,
                        receipt.created_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    f"duplicate apply receipt: {receipt.apply_id}"
                ) from exc
            self._conn.commit()

    def receipts(
        self,
        artifact_id: str | None = None,
    ) -> tuple[PromotionApplyReceipt, ...]:
        with self._lock:
            if artifact_id is None:
                rows = self._conn.execute(
                    """
                    SELECT * FROM promotion_apply_receipts
                    ORDER BY created_at, apply_id
                    """
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT * FROM promotion_apply_receipts
                    WHERE artifact_id = ?
                    ORDER BY created_at, apply_id
                    """,
                    (artifact_id,),
                ).fetchall()
        return tuple(_receipt_from_row(row) for row in rows)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "SQLitePromotionPort":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def _artifact_values(artifact: PromotionArtifact) -> tuple[object, ...]:
    return (
        artifact.artifact_id,
        artifact.candidate_id,
        artifact.kind,
        artifact.target,
        artifact.title,
        artifact.content,
        artifact.version,
        json.dumps(list(artifact.source_episode_ids), ensure_ascii=False),
        json.dumps(list(artifact.evidence_refs), ensure_ascii=False),
        artifact.validation_run_id,
        json.dumps(list(artifact.trigger_conditions), ensure_ascii=False),
        artifact.scope,
        artifact.risk_class,
        artifact.created_at,
        artifact.state,
        artifact.invalidated_at,
        artifact.invalidation_reason,
        artifact.schema_version,
    )


def _artifact_from_row(row: sqlite3.Row) -> PromotionArtifact:
    return PromotionArtifact(
        artifact_id=row["artifact_id"],
        candidate_id=row["candidate_id"],
        kind=row["kind"],
        target=row["target"],
        title=row["title"],
        content=row["content"],
        version=row["version"],
        source_episode_ids=tuple(json.loads(row["source_episode_ids_json"])),
        evidence_refs=tuple(json.loads(row["evidence_refs_json"])),
        validation_run_id=row["validation_run_id"],
        trigger_conditions=tuple(json.loads(row["trigger_conditions_json"])),
        scope=row["scope"],
        risk_class=row["risk_class"],
        created_at=float(row["created_at"]),
        state=row["state"],
        invalidated_at=(
            None if row["invalidated_at"] is None
            else float(row["invalidated_at"])
        ),
        invalidation_reason=row["invalidation_reason"],
        schema_version=int(row["schema_version"]),
    )


def _receipt_from_row(row: sqlite3.Row) -> PromotionApplyReceipt:
    return PromotionApplyReceipt(
        apply_id=row["apply_id"],
        artifact_id=row["artifact_id"],
        target=row["target"],
        target_ref=row["target_ref"],
        actor=row["actor"],
        approval_ref=row["approval_ref"],
        reason=row["reason"],
        status=row["status"],
        result_ref=row["result_ref"],
        created_at=float(row["created_at"]),
    )
