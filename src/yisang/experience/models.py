from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import time
from typing import Any

EXPERIENCE_SCHEMA_VERSION = 1
EXPERIENCE_OUTCOMES = frozenset({"success", "failure"})
EXPERIENCE_RISK_CLASSES = frozenset(
    {"normal", "privileged", "security_sensitive"}
)
EXPERIENCE_VALIDATION_METHODS = frozenset(
    {"external", "manual", "test", "replay"}
)
EXPERIENCE_CANDIDATE_STATUSES = frozenset(
    {"candidate", "promoted", "needs_review", "blocked", "revoked"}
)


@dataclass(frozen=True)
class ExperienceObservation:
    """One piece of experiential evidence.

    Observations are evidence. They are never durable capability by themselves.
    A promotion engine must aggregate distinct evidence and pass a promotion gate.
    """

    evidence_id: str
    target_book_id: str
    target_entry_id: str
    lesson: str
    applies_when: tuple[str, ...] = ()
    outcome: str = "success"
    verified: bool = False
    verification_ref: str | None = None
    validation_method: str = "external"
    risk_class: str = "normal"
    source_episode_id: str | None = None
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = EXPERIENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("evidence_id must be non-empty")
        if not self.target_book_id.strip():
            raise ValueError("target_book_id must be non-empty")
        if not self.target_entry_id.strip():
            raise ValueError("target_entry_id must be non-empty")
        if not self.lesson.strip():
            raise ValueError("lesson must be non-empty")
        if self.outcome not in EXPERIENCE_OUTCOMES:
            raise ValueError(f"unsupported outcome: {self.outcome}")
        if self.validation_method not in EXPERIENCE_VALIDATION_METHODS:
            raise ValueError(
                f"unsupported validation_method: {self.validation_method}"
            )
        if self.risk_class not in EXPERIENCE_RISK_CLASSES:
            raise ValueError(f"unsupported risk_class: {self.risk_class}")
        if self.schema_version <= 0:
            raise ValueError("schema_version must be positive")
        if self.verified and not (self.verification_ref or "").strip():
            raise ValueError(
                "verified observations require a non-empty verification_ref"
            )
        if self.validation_method == "replay":
            if not (self.verification_ref or "").startswith("replay:"):
                raise ValueError(
                    "replay validation requires a replay: verification_ref"
                )
            if not (self.source_episode_id or "").strip():
                raise ValueError(
                    "replay validation requires source_episode_id"
                )

    @property
    def candidate_key(self) -> str:
        payload = {
            "target_book_id": self.target_book_id.strip(),
            "target_entry_id": self.target_entry_id.strip(),
            "lesson": " ".join(self.lesson.split()),
            "applies_when": list(_normalized_strings(self.applies_when)),
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"exp_{sha256(encoded).hexdigest()[:20]}"


@dataclass(frozen=True)
class ExperienceCandidate:
    candidate_key: str
    target_book_id: str
    target_entry_id: str
    lesson: str
    applies_when: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    verification_refs: tuple[str, ...] = ()
    source_episode_ids: tuple[str, ...] = ()
    success_count: int = 0
    failure_count: int = 0
    risk_class: str = "normal"
    status: str = "candidate"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    schema_version: int = EXPERIENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.candidate_key.strip():
            raise ValueError("candidate_key must be non-empty")
        if not self.target_book_id.strip():
            raise ValueError("target_book_id must be non-empty")
        if not self.target_entry_id.strip():
            raise ValueError("target_entry_id must be non-empty")
        if not self.lesson.strip():
            raise ValueError("lesson must be non-empty")
        if self.success_count < 0 or self.failure_count < 0:
            raise ValueError("experience counters must be non-negative")
        if self.risk_class not in EXPERIENCE_RISK_CLASSES:
            raise ValueError(f"unsupported risk_class: {self.risk_class}")
        if self.status not in EXPERIENCE_CANDIDATE_STATUSES:
            raise ValueError(f"unsupported candidate status: {self.status}")
        if self.schema_version <= 0:
            raise ValueError("schema_version must be positive")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("evidence_ids must be unique")
        if len(set(self.verification_refs)) != len(self.verification_refs):
            raise ValueError("verification_refs must be unique")
        if len(set(self.source_episode_ids)) != len(self.source_episode_ids):
            raise ValueError("source_episode_ids must be unique")

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_key": self.candidate_key,
            "target_book_id": self.target_book_id,
            "target_entry_id": self.target_entry_id,
            "lesson": self.lesson,
            "applies_when": list(self.applies_when),
            "evidence_ids": list(self.evidence_ids),
            "verification_refs": list(self.verification_refs),
            "source_episode_ids": list(self.source_episode_ids),
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "risk_class": self.risk_class,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExperienceCandidate":
        return cls(
            candidate_key=str(data["candidate_key"]),
            target_book_id=str(data["target_book_id"]),
            target_entry_id=str(data["target_entry_id"]),
            lesson=str(data["lesson"]),
            applies_when=_normalized_strings(data.get("applies_when", ())),
            evidence_ids=_normalized_strings(data.get("evidence_ids", ())),
            verification_refs=_normalized_strings(
                data.get("verification_refs", ())
            ),
            source_episode_ids=_normalized_strings(
                data.get("source_episode_ids", ())
            ),
            success_count=int(data.get("success_count", 0)),
            failure_count=int(data.get("failure_count", 0)),
            risk_class=str(data.get("risk_class", "normal")),
            status=str(data.get("status", "candidate")),
            created_at=float(data.get("created_at", 0.0)),
            updated_at=float(data.get("updated_at", 0.0)),
            schema_version=int(
                data.get("schema_version", EXPERIENCE_SCHEMA_VERSION)
            ),
        )


@dataclass(frozen=True)
class ExperiencePromotionResult:
    status: str
    reason: str
    candidate: ExperienceCandidate | None = None
    promoted: bool = False
    reinforced: bool = False


def _normalized_strings(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    return tuple(
        dict.fromkeys(
            str(value).strip()
            for value in values
            if str(value).strip()
        )
    )
