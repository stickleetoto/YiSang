from __future__ import annotations
import json
from pathlib import Path
import sqlite3
from threading import RLock
from .episode_port import ExperiencePort
from .models import ExperienceEpisode, ExperienceEvidence

class SQLiteExperiencePort(ExperiencePort):
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS experience_episodes (
                    episode_id TEXT PRIMARY KEY,
                    outcome TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    trigger_conditions_json TEXT NOT NULL,
                    procedure_steps_json TEXT NOT NULL,
                    request_id TEXT NOT NULL DEFAULT '',
                    engine_id TEXT NOT NULL DEFAULT '',
                    verification_status TEXT NOT NULL DEFAULT '',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    schema_version INTEGER NOT NULL
                )
            """)
            self._conn.commit()

    def put_episode(self, episode: ExperienceEpisode) -> None:
        evidence=[{
            "evidence_ref":e.evidence_ref,"source_type":e.source_type,
            "summary":e.summary,"verified":e.verified
        } for e in episode.evidence]
        with self._lock:
            try:
                self._conn.execute("""
                    INSERT INTO experience_episodes (
                        episode_id,outcome,summary,evidence_json,
                        trigger_conditions_json,procedure_steps_json,
                        request_id,engine_id,verification_status,
                        metadata_json,created_at,schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,(
                    episode.episode_id,episode.outcome,episode.summary,
                    json.dumps(evidence,ensure_ascii=False),
                    json.dumps(list(episode.trigger_conditions),ensure_ascii=False),
                    json.dumps(list(episode.procedure_steps),ensure_ascii=False),
                    episode.request_id,episode.engine_id,episode.verification_status,
                    json.dumps(episode.metadata,ensure_ascii=False,sort_keys=True),
                    episode.created_at,episode.schema_version,
                ))
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"duplicate experience episode: {episode.episode_id}") from exc
            self._conn.commit()

    def get_episode(self, episode_id: str) -> ExperienceEpisode | None:
        with self._lock:
            row=self._conn.execute(
                "SELECT * FROM experience_episodes WHERE episode_id = ?",
                (episode_id,)
            ).fetchone()
        return None if row is None else _episode_from_row(row)

    def list_episodes(self) -> tuple[ExperienceEpisode, ...]:
        with self._lock:
            rows=self._conn.execute(
                "SELECT * FROM experience_episodes ORDER BY created_at, episode_id"
            ).fetchall()
        return tuple(_episode_from_row(row) for row in rows)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "SQLiteExperiencePort":
        return self

    def __exit__(self,*_args:object)->None:
        self.close()

def _episode_from_row(row:sqlite3.Row)->ExperienceEpisode:
    evidence=tuple(ExperienceEvidence(
        evidence_ref=str(x["evidence_ref"]),source_type=str(x["source_type"]),
        summary=str(x["summary"]),verified=bool(x.get("verified",False))
    ) for x in json.loads(row["evidence_json"]))
    return ExperienceEpisode(
        episode_id=row["episode_id"],outcome=row["outcome"],summary=row["summary"],
        evidence=evidence,
        trigger_conditions=tuple(json.loads(row["trigger_conditions_json"])),
        procedure_steps=tuple(json.loads(row["procedure_steps_json"])),
        request_id=row["request_id"],engine_id=row["engine_id"],
        verification_status=row["verification_status"],
        metadata=dict(json.loads(row["metadata_json"])),
        created_at=float(row["created_at"]),schema_version=int(row["schema_version"])
    )
