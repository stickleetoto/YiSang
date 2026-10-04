from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from threading import RLock
import time
from typing import Any
import uuid

EPISODE_SCHEMA_VERSION = 1
EPISODE_OUTCOMES = frozenset({"success", "failure", "unknown"})


@dataclass(frozen=True)
class EpisodeStep:
    step_id: str
    kind: str
    status: str
    action: str | None = None
    side_effect_id: str | None = None
    evidence_refs: tuple[str, ...] = ()
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.step_id.strip():
            raise ValueError("step_id must be non-empty")
        if not self.kind.strip():
            raise ValueError("kind must be non-empty")
        if not self.status.strip():
            raise ValueError("status must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "kind": self.kind,
            "status": self.status,
            "action": self.action,
            "side_effect_id": self.side_effect_id,
            "evidence_refs": list(self.evidence_refs),
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EpisodeStep":
        return cls(
            step_id=str(data["step_id"]),
            kind=str(data["kind"]),
            status=str(data["status"]),
            action=(
                str(data["action"])
                if data.get("action") is not None
                else None
            ),
            side_effect_id=(
                str(data["side_effect_id"])
                if data.get("side_effect_id") is not None
                else None
            ),
            evidence_refs=tuple(
                str(item) for item in data.get("evidence_refs", ())
            ),
            data=dict(data.get("data", {})),
        )


@dataclass(frozen=True)
class EpisodeRecord:
    episode_id: str
    request_id: str
    goal: str
    outcome: str
    steps: tuple[EpisodeStep, ...] = ()
    verification_refs: tuple[str, ...] = ()
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = EPISODE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.episode_id.strip():
            raise ValueError("episode_id must be non-empty")
        if not self.request_id.strip():
            raise ValueError("request_id must be non-empty")
        if not self.goal.strip():
            raise ValueError("goal must be non-empty")
        if self.outcome not in EPISODE_OUTCOMES:
            raise ValueError(f"unsupported episode outcome: {self.outcome}")
        if self.schema_version <= 0:
            raise ValueError("schema_version must be positive")
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("episode step_id values must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "request_id": self.request_id,
            "goal": self.goal,
            "outcome": self.outcome,
            "steps": [step.to_dict() for step in self.steps],
            "verification_refs": list(self.verification_refs),
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EpisodeRecord":
        return cls(
            episode_id=str(data["episode_id"]),
            request_id=str(data["request_id"]),
            goal=str(data["goal"]),
            outcome=str(data["outcome"]),
            steps=tuple(
                EpisodeStep.from_dict(dict(item))
                for item in data.get("steps", ())
            ),
            verification_refs=tuple(
                str(item) for item in data.get("verification_refs", ())
            ),
            created_at=float(data.get("created_at", 0.0)),
            metadata=dict(data.get("metadata", {})),
            schema_version=int(
                data.get("schema_version", EPISODE_SCHEMA_VERSION)
            ),
        )

    def fingerprint(self) -> str:
        payload = self.to_dict()
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return sha256(encoded).hexdigest()


class EpisodePort(ABC):
    @abstractmethod
    def get(self, episode_id: str) -> EpisodeRecord | None:
        raise NotImplementedError

    @abstractmethod
    def put(self, episode: EpisodeRecord) -> None:
        raise NotImplementedError

    @abstractmethod
    def all(self) -> tuple[EpisodeRecord, ...]:
        raise NotImplementedError


class InMemoryEpisodePort(EpisodePort):
    def __init__(self) -> None:
        self._items: dict[str, EpisodeRecord] = {}

    def get(self, episode_id: str) -> EpisodeRecord | None:
        return self._items.get(episode_id)

    def put(self, episode: EpisodeRecord) -> None:
        self._items[episode.episode_id] = episode

    def all(self) -> tuple[EpisodeRecord, ...]:
        return tuple(self._items[key] for key in sorted(self._items))


class SQLiteEpisodePort(EpisodePort):
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experience_episodes (
                    episode_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    fingerprint TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def get(self, episode_id: str) -> EpisodeRecord | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT payload_json, fingerprint
                FROM experience_episodes
                WHERE episode_id = ?
                """,
                (episode_id,),
            ).fetchone()
        if row is None:
            return None
        episode = EpisodeRecord.from_dict(
            json.loads(str(row["payload_json"]))
        )
        if episode.fingerprint() != str(row["fingerprint"]):
            raise ValueError(f"episode fingerprint mismatch: {episode_id}")
        return episode

    def put(self, episode: EpisodeRecord) -> None:
        payload = json.dumps(
            episode.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        fingerprint = episode.fingerprint()
        with self._lock:
            existing = self._conn.execute(
                """
                SELECT fingerprint
                FROM experience_episodes
                WHERE episode_id = ?
                """,
                (episode.episode_id,),
            ).fetchone()
            if existing is not None and str(existing["fingerprint"]) != fingerprint:
                raise ValueError(
                    f"episode_id collision with different content: "
                    f"{episode.episode_id}"
                )
            self._conn.execute(
                """
                INSERT INTO experience_episodes(
                    episode_id, payload_json, fingerprint
                ) VALUES (?, ?, ?)
                ON CONFLICT(episode_id)
                DO UPDATE SET
                    payload_json = excluded.payload_json,
                    fingerprint = excluded.fingerprint
                """,
                (episode.episode_id, payload, fingerprint),
            )
            self._conn.commit()

    def all(self) -> tuple[EpisodeRecord, ...]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT episode_id
                FROM experience_episodes
                ORDER BY episode_id ASC
                """
            ).fetchall()
        return tuple(
            episode
            for row in rows
            if (episode := self.get(str(row["episode_id"]))) is not None
        )


def build_runtime_episode(
    *,
    request_id: str,
    goal: str,
    engine_id: str,
    verification_status: str,
    verification_reason: str,
    action_results: tuple[dict[str, Any], ...] | list[dict[str, Any]] = (),
    active_project: str | None = None,
) -> EpisodeRecord:
    """Build a compact episode from one completed YiSang Runtime request.

    Raw tool output is intentionally excluded. The episode keeps action outcome,
    gate/failure summaries, completion evidence, and verifier identity evidence.
    """
    steps: list[EpisodeStep] = []
    for index, item in enumerate(action_results, start=1):
        if not isinstance(item, dict):
            continue
        failure = item.get("failure")
        completion_evidence = item.get("completion_evidence")
        steps.append(
            EpisodeStep(
                step_id=f"action-{index:03d}",
                kind="action",
                status=str(item.get("status", "UNKNOWN")),
                action=str(item.get("tool_id", "unknown")),
                evidence_refs=_runtime_evidence_refs(item),
                data={
                    "gate_reason": str(item.get("gate_reason", "")),
                    "error": item.get("error"),
                    "failure": (
                        dict(failure)
                        if isinstance(failure, dict)
                        else None
                    ),
                    "goal_satisfied": bool(
                        item.get("goal_satisfied", False)
                    ),
                    "completion_evidence": (
                        dict(completion_evidence)
                        if isinstance(completion_evidence, dict)
                        else {}
                    ),
                },
            )
        )

    verification_ref = (
        f"verifier:{verification_status}:{verification_reason}"
    )
    steps.append(
        EpisodeStep(
            step_id="verification",
            kind="verification",
            status=verification_status,
            evidence_refs=(verification_ref,),
            data={"reason": verification_reason},
        )
    )

    return EpisodeRecord(
        episode_id=f"ep-{uuid.uuid4().hex[:12]}",
        request_id=request_id,
        goal=goal,
        outcome=(
            "success"
            if verification_status == "PASS"
            else "failure"
        ),
        steps=tuple(steps),
        verification_refs=(verification_ref,),
        metadata={
            "engine_id": engine_id,
            "active_project": active_project,
        },
    )


def _runtime_evidence_refs(item: dict[str, Any]) -> tuple[str, ...]:
    refs: list[str] = []
    tool_id = str(item.get("tool_id", "unknown"))
    status = str(item.get("status", "UNKNOWN"))
    refs.append(f"action:{tool_id}:{status}")

    completion_evidence = item.get("completion_evidence")
    if isinstance(completion_evidence, dict):
        for key, value in sorted(completion_evidence.items()):
            refs.append(f"completion:{key}={value}")

    return tuple(refs)
