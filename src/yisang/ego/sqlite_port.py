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
from .port import EgoPort, InstalledEgoPackage


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
            self._conn.commit()

    def install(
        self,
        package: InstalledEgoPackage,
        *,
        supersede_active: bool = True,
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
            self._conn.commit()
        item = self.get(ego_id, to_version)
        assert item is not None
        return item

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
