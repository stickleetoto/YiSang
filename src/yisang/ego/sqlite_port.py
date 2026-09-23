from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
from threading import RLock
import time
from typing import Any

from .models import EgoManifest, EgoRiskHints
from .package import semantic_version_key
from .port import (
    EgoAuditEvent,
    EgoInvalidationCandidate,
    EgoPort,
    InstalledEgoPackage,
)


class SQLiteEgoPort(EgoPort):
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
                CREATE TABLE IF NOT EXISTS ego_packages (
                    ego_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    manifest_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    source_artifact_id TEXT,
                    approval_ref TEXT,
                    superseded_by_version TEXT,
                    status_reason TEXT NOT NULL,
                    installed_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (ego_id, version)
                )
                """
            )
            self._conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_ego_source_artifact
                ON ego_packages(source_artifact_id)
                WHERE source_artifact_id IS NOT NULL
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ego_audit_events (
                    event_id TEXT PRIMARY KEY,
                    action TEXT NOT NULL,
                    ego_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    approval_ref TEXT,
                    related_version TEXT,
                    candidate_id TEXT,
                    metadata_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ego_invalidation_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    ego_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    replay_run_id TEXT NOT NULL,
                    failed_tests_json TEXT NOT NULL,
                    evidence_refs_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    source_artifact_id TEXT,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    resolved_at REAL,
                    resolution_actor TEXT,
                    approval_ref TEXT,
                    resolution_reason TEXT
                )
                """
            )
            self._conn.commit()

    def install(
        self,
        package: InstalledEgoPackage,
        *,
        supersede_active: bool = True,
        actor: str = "system",
        approval_ref: str | None = None,
    ) -> InstalledEgoPackage:
        now = time.time()
        installed = InstalledEgoPackage(
            ego_id=package.ego_id,
            version=package.version,
            manifest=package.manifest,
            state="active",
            source_artifact_id=package.source_artifact_id,
            approval_ref=package.approval_ref,
            superseded_by_version=None,
            status_reason=package.status_reason,
            installed_at=package.installed_at,
            updated_at=now,
        )
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                if supersede_active:
                    old_rows = self._conn.execute(
                        """
                        SELECT ego_id, version FROM ego_packages
                        WHERE ego_id = ? AND state = 'active'
                        """,
                        (installed.ego_id,),
                    ).fetchall()
                    self._conn.execute(
                        """
                        UPDATE ego_packages
                        SET state = 'superseded',
                            superseded_by_version = ?,
                            status_reason = ?,
                            updated_at = ?
                        WHERE ego_id = ? AND state = 'active'
                        """,
                        (
                            installed.version,
                            f"superseded by {installed.version}",
                            now,
                            installed.ego_id,
                        ),
                    )
                    for old_row in old_rows:
                        self._insert_audit_locked(
                            EgoAuditEvent(
                                event_id=f"ego-event-{__import__('uuid').uuid4().hex[:12]}",
                                action="supersede",
                                ego_id=old_row["ego_id"],
                                version=old_row["version"],
                                actor=actor,
                                reason=f"superseded by {installed.version}",
                                approval_ref=approval_ref,
                                related_version=installed.version,
                            )
                        )
                self._conn.execute(
                    """
                    INSERT INTO ego_packages (
                        ego_id, version, manifest_json, state,
                        source_artifact_id, approval_ref,
                        superseded_by_version, status_reason,
                        installed_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        installed.ego_id,
                        installed.version,
                        json.dumps(
                            _manifest_to_dict(installed.manifest),
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        installed.state,
                        installed.source_artifact_id,
                        installed.approval_ref,
                        installed.superseded_by_version,
                        installed.status_reason,
                        installed.installed_at,
                        installed.updated_at,
                    ),
                )
                self._insert_audit_locked(
                    EgoAuditEvent(
                        event_id=f"ego-event-{__import__('uuid').uuid4().hex[:12]}",
                        action="install",
                        ego_id=installed.ego_id,
                        version=installed.version,
                        actor=actor,
                        reason=installed.status_reason or "installed E.G.O package",
                        approval_ref=approval_ref or installed.approval_ref,
                        metadata={
                            "source_artifact_id": installed.source_artifact_id,
                            "package_digest": installed.manifest.package_digest,
                        },
                    )
                )
                self._conn.commit()
            except sqlite3.IntegrityError as exc:
                self._conn.rollback()
                raise ValueError(
                    f"duplicate/conflicting E.G.O install: "
                    f"{installed.ego_id}@{installed.version}"
                ) from exc
            except Exception:
                self._conn.rollback()
                raise
        return installed

    def get(
        self,
        ego_id: str,
        version: str | None = None,
    ) -> InstalledEgoPackage | None:
        if version is not None:
            with self._lock:
                row = self._conn.execute(
                    """
                    SELECT * FROM ego_packages
                    WHERE ego_id = ? AND version = ?
                    """,
                    (ego_id, version),
                ).fetchone()
            return None if row is None else _from_row(row)

        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM ego_packages WHERE ego_id = ?",
                (ego_id,),
            ).fetchall()
        items = tuple(_from_row(row) for row in rows)
        active = tuple(item for item in items if item.active)
        if active:
            return max(active, key=lambda item: semantic_version_key(item.version))
        return (
            max(items, key=lambda item: semantic_version_key(item.version))
            if items
            else None
        )

    def list_versions(self, ego_id: str) -> tuple[InstalledEgoPackage, ...]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM ego_packages WHERE ego_id = ?",
                (ego_id,),
            ).fetchall()
        return tuple(
            sorted(
                (_from_row(row) for row in rows),
                key=lambda item: semantic_version_key(item.version),
            )
        )

    def list_active(self) -> tuple[InstalledEgoPackage, ...]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM ego_packages WHERE state = 'active'"
            ).fetchall()
        return tuple(
            sorted(
                (_from_row(row) for row in rows),
                key=lambda item: (
                    item.ego_id,
                    semantic_version_key(item.version),
                ),
            )
        )

    def disable(
        self,
        ego_id: str,
        version: str,
        *,
        reason: str,
        actor: str = "system",
        approval_ref: str | None = None,
    ) -> InstalledEgoPackage:
        normalized = reason.strip()
        if not normalized:
            raise ValueError("reason must be non-empty")
        with self._lock:
            cursor = self._conn.execute(
                """
                UPDATE ego_packages
                SET state='disabled',
                    superseded_by_version=NULL,
                    status_reason=?,
                    updated_at=?
                WHERE ego_id=? AND version=?
                """,
                (normalized, time.time(), ego_id, version),
            )
            if cursor.rowcount != 1:
                self._conn.rollback()
                raise KeyError(f"{ego_id}@{version}")
            self._insert_audit_locked(
                EgoAuditEvent(
                    event_id=f"ego-event-{__import__('uuid').uuid4().hex[:12]}",
                    action="disable",
                    ego_id=ego_id,
                    version=version,
                    actor=actor,
                    reason=normalized,
                    approval_ref=approval_ref,
                )
            )
            self._conn.commit()
        item = self.get(ego_id, version)
        assert item is not None
        return item

    def rollback(
        self,
        ego_id: str,
        to_version: str,
        *,
        reason: str,
        actor: str = "system",
        approval_ref: str | None = None,
    ) -> InstalledEgoPackage:
        normalized = reason.strip()
        if not normalized:
            raise ValueError("reason must be non-empty")
        with self._lock:
            target = self._conn.execute(
                """
                SELECT 1 FROM ego_packages
                WHERE ego_id=? AND version=?
                """,
                (ego_id, to_version),
            ).fetchone()
            if target is None:
                raise KeyError(f"{ego_id}@{to_version}")
            now = time.time()
            old_active_rows = self._conn.execute(
                """
                SELECT ego_id, version FROM ego_packages
                WHERE ego_id=? AND state='active' AND version<>?
                """,
                (ego_id, to_version),
            ).fetchall()
            self._conn.execute("BEGIN IMMEDIATE")
            self._conn.execute(
                """
                UPDATE ego_packages
                SET state='superseded',
                    superseded_by_version=?,
                    status_reason=?,
                    updated_at=?
                WHERE ego_id=? AND state='active' AND version<>?
                """,
                (
                    to_version,
                    f"rollback: {normalized}",
                    now,
                    ego_id,
                    to_version,
                ),
            )
            for old_row in old_active_rows:
                self._insert_audit_locked(
                    EgoAuditEvent(
                        event_id=f"ego-event-{__import__('uuid').uuid4().hex[:12]}",
                        action="supersede",
                        ego_id=old_row["ego_id"],
                        version=old_row["version"],
                        actor=actor,
                        reason=f"rollback: {normalized}",
                        approval_ref=approval_ref,
                        related_version=to_version,
                    )
                )
            self._conn.execute(
                """
                UPDATE ego_packages
                SET state='active',
                    superseded_by_version=NULL,
                    status_reason=?,
                    updated_at=?
                WHERE ego_id=? AND version=?
                """,
                (
                    f"rollback target: {normalized}",
                    now,
                    ego_id,
                    to_version,
                ),
            )
            self._insert_audit_locked(
                EgoAuditEvent(
                    event_id=f"ego-event-{__import__('uuid').uuid4().hex[:12]}",
                    action="rollback",
                    ego_id=ego_id,
                    version=to_version,
                    actor=actor,
                    reason=normalized,
                    approval_ref=approval_ref,
                )
            )
            self._conn.commit()
        item = self.get(ego_id, to_version)
        assert item is not None
        return item

    def record_audit(self, event: EgoAuditEvent) -> None:
        with self._lock:
            try:
                self._insert_audit_locked(event)
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    f"duplicate E.G.O audit event: {event.event_id}"
                ) from exc
            self._conn.commit()

    def _insert_audit_locked(self, event: EgoAuditEvent) -> None:
        self._conn.execute(
            """
            INSERT INTO ego_audit_events (
                event_id, action, ego_id, version, actor, reason,
                approval_ref, related_version, candidate_id,
                metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.action,
                event.ego_id,
                event.version,
                event.actor,
                event.reason,
                event.approval_ref,
                event.related_version,
                event.candidate_id,
                json.dumps(event.metadata, ensure_ascii=False, sort_keys=True),
                event.created_at,
            ),
        )

    def audit_events(
        self,
        ego_id: str | None = None,
    ) -> tuple[EgoAuditEvent, ...]:
        with self._lock:
            if ego_id is None:
                rows = self._conn.execute(
                    "SELECT * FROM ego_audit_events ORDER BY created_at, event_id"
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT * FROM ego_audit_events
                    WHERE ego_id=?
                    ORDER BY created_at, event_id
                    """,
                    (ego_id,),
                ).fetchall()
        return tuple(_audit_from_row(row) for row in rows)

    def put_invalidation_candidate(
        self,
        candidate: EgoInvalidationCandidate,
    ) -> None:
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO ego_invalidation_candidates (
                        candidate_id, ego_id, version, replay_run_id,
                        failed_tests_json, evidence_refs_json, reason,
                        source_artifact_id, status, created_at, resolved_at,
                        resolution_actor, approval_ref, resolution_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        candidate.candidate_id,
                        candidate.ego_id,
                        candidate.version,
                        candidate.replay_run_id,
                        json.dumps(candidate.failed_tests),
                        json.dumps(candidate.evidence_refs),
                        candidate.reason,
                        candidate.source_artifact_id,
                        candidate.status,
                        candidate.created_at,
                        candidate.resolved_at,
                        candidate.resolution_actor,
                        candidate.approval_ref,
                        candidate.resolution_reason,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(
                    f"duplicate E.G.O invalidation candidate: "
                    f"{candidate.candidate_id}"
                ) from exc
            self._conn.commit()

    def get_invalidation_candidate(
        self,
        candidate_id: str,
    ) -> EgoInvalidationCandidate | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM ego_invalidation_candidates
                WHERE candidate_id=?
                """,
                (candidate_id,),
            ).fetchone()
        return None if row is None else _candidate_from_row(row)

    def list_invalidation_candidates(
        self,
        *,
        status: str | None = None,
    ) -> tuple[EgoInvalidationCandidate, ...]:
        with self._lock:
            if status is None:
                rows = self._conn.execute(
                    """
                    SELECT * FROM ego_invalidation_candidates
                    ORDER BY created_at, candidate_id
                    """
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT * FROM ego_invalidation_candidates
                    WHERE status=?
                    ORDER BY created_at, candidate_id
                    """,
                    (status,),
                ).fetchall()
        return tuple(_candidate_from_row(row) for row in rows)

    def update_invalidation_candidate(
        self,
        candidate: EgoInvalidationCandidate,
    ) -> None:
        with self._lock:
            cursor = self._conn.execute(
                """
                UPDATE ego_invalidation_candidates
                SET status=?, resolved_at=?, resolution_actor=?,
                    approval_ref=?, resolution_reason=?
                WHERE candidate_id=?
                """,
                (
                    candidate.status,
                    candidate.resolved_at,
                    candidate.resolution_actor,
                    candidate.approval_ref,
                    candidate.resolution_reason,
                    candidate.candidate_id,
                ),
            )
            if cursor.rowcount != 1:
                self._conn.rollback()
                raise KeyError(candidate.candidate_id)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "SQLiteEgoPort":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def _manifest_to_dict(manifest: EgoManifest) -> dict[str, Any]:
    payload = asdict(manifest)
    return payload


def _manifest_from_dict(raw: dict[str, Any]) -> EgoManifest:
    risk_raw = raw.get("risk") or {}
    return EgoManifest(
        ego_id=str(raw["ego_id"]),
        name=str(raw["name"]),
        provides=tuple(str(x) for x in raw.get("provides", [])),
        keywords=tuple(str(x) for x in raw.get("keywords", [])),
        instructions=str(raw.get("instructions", "")),
        permissions=dict(raw.get("permissions", {})),
        schema_version=int(raw.get("schema_version", 1)),
        version=str(raw.get("version", "1.0.0")),
        description=str(raw.get("description", "")),
        tags=tuple(str(x) for x in raw.get("tags", [])),
        examples=tuple(str(x) for x in raw.get("examples", [])),
        requires=tuple(str(x) for x in raw.get("requires", [])),
        conflicts=tuple(str(x) for x in raw.get("conflicts", [])),
        risk=EgoRiskHints(
            read_only=bool(risk_raw.get("read_only", False)),
            destructive=bool(risk_raw.get("destructive", True)),
            idempotent=bool(risk_raw.get("idempotent", False)),
            open_world=bool(risk_raw.get("open_world", True)),
        ),
        runtime_type=str(raw.get("runtime_type", "prompt")),
        input_schema=raw.get("input_schema"),
        output_schema=raw.get("output_schema"),
        resources=tuple(str(x) for x in raw.get("resources", [])),
        evals=tuple(str(x) for x in raw.get("evals", [])),
        package_digest=raw.get("package_digest"),
        detail_level=str(raw.get("detail_level", "full")),
    )


def _from_row(row: sqlite3.Row) -> InstalledEgoPackage:
    return InstalledEgoPackage(
        ego_id=row["ego_id"],
        version=row["version"],
        manifest=_manifest_from_dict(json.loads(row["manifest_json"])),
        state=row["state"],
        source_artifact_id=row["source_artifact_id"],
        approval_ref=row["approval_ref"],
        superseded_by_version=row["superseded_by_version"],
        status_reason=row["status_reason"],
        installed_at=float(row["installed_at"]),
        updated_at=float(row["updated_at"]),
    )



def _audit_from_row(row: sqlite3.Row) -> EgoAuditEvent:
    return EgoAuditEvent(
        event_id=row["event_id"],
        action=row["action"],
        ego_id=row["ego_id"],
        version=row["version"],
        actor=row["actor"],
        reason=row["reason"],
        approval_ref=row["approval_ref"],
        related_version=row["related_version"],
        candidate_id=row["candidate_id"],
        metadata=json.loads(row["metadata_json"]),
        created_at=float(row["created_at"]),
    )


def _candidate_from_row(row: sqlite3.Row) -> EgoInvalidationCandidate:
    return EgoInvalidationCandidate(
        candidate_id=row["candidate_id"],
        ego_id=row["ego_id"],
        version=row["version"],
        replay_run_id=row["replay_run_id"],
        failed_tests=tuple(json.loads(row["failed_tests_json"])),
        evidence_refs=tuple(json.loads(row["evidence_refs_json"])),
        reason=row["reason"],
        source_artifact_id=row["source_artifact_id"],
        status=row["status"],
        created_at=float(row["created_at"]),
        resolved_at=(
            float(row["resolved_at"])
            if row["resolved_at"] is not None
            else None
        ),
        resolution_actor=row["resolution_actor"],
        approval_ref=row["approval_ref"],
        resolution_reason=row["resolution_reason"],
    )
