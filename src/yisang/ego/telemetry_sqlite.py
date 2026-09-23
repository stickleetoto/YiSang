from __future__ import annotations

from pathlib import Path
import sqlite3
from threading import RLock

from .telemetry import EgoTelemetryEvent, EgoTelemetryPort


class SQLiteEgoTelemetryPort(EgoTelemetryPort):
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ego_telemetry (
                    event_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    ego_id TEXT NOT NULL,
                    version TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    request_ref TEXT NOT NULL,
                    verification_status TEXT NOT NULL,
                    latency_ms REAL,
                    action_failure_count INTEGER NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_ego_telemetry_target
                ON ego_telemetry(ego_id, version, created_at)
                """
            )
            self._conn.commit()

    def record(self, event: EgoTelemetryEvent) -> EgoTelemetryEvent:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM ego_telemetry WHERE event_id=?",
                (event.event_id,),
            ).fetchone()
            if row is not None:
                existing = _from_row(row)
                if existing != event:
                    raise ValueError(
                        f"conflicting E.G.O telemetry event: {event.event_id}"
                    )
                return existing
            self._conn.execute(
                """
                INSERT INTO ego_telemetry (
                    event_id, kind, ego_id, version, success,
                    request_ref, verification_status, latency_ms,
                    action_failure_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.kind,
                    event.ego_id,
                    event.version,
                    int(event.success),
                    event.request_ref,
                    event.verification_status,
                    event.latency_ms,
                    event.action_failure_count,
                    event.created_at,
                ),
            )
            self._conn.commit()
        return event

    def events(
        self,
        *,
        ego_id: str | None = None,
        version: str | None = None,
    ) -> tuple[EgoTelemetryEvent, ...]:
        clauses: list[str] = []
        params: list[str] = []
        if ego_id is not None:
            clauses.append("ego_id=?")
            params.append(ego_id)
        if version is not None:
            clauses.append("version=?")
            params.append(version)
        where = (
            " WHERE " + " AND ".join(clauses)
            if clauses
            else ""
        )
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM ego_telemetry"
                + where
                + " ORDER BY created_at, event_id",
                tuple(params),
            ).fetchall()
        return tuple(_from_row(row) for row in rows)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "SQLiteEgoTelemetryPort":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def _from_row(row: sqlite3.Row) -> EgoTelemetryEvent:
    return EgoTelemetryEvent(
        event_id=row["event_id"],
        kind=row["kind"],
        ego_id=row["ego_id"],
        version=row["version"],
        success=bool(row["success"]),
        request_ref=row["request_ref"],
        verification_status=row["verification_status"],
        latency_ms=(
            float(row["latency_ms"])
            if row["latency_ms"] is not None
            else None
        ),
        action_failure_count=int(row["action_failure_count"]),
        created_at=float(row["created_at"]),
    )
