from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
import time
import uuid
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


# ---------------------------------------------------------------------------
# Legacy v0.7 promotion compatibility
#
# E.G.O v2 was developed against an earlier promotion-artifact API.  These
# structures remain a compatibility boundary only; the authoritative learning
# path is ExperienceObservation -> ExperiencePromotionEngine.
# ---------------------------------------------------------------------------

LEGACY_EVIDENCE_SOURCE_TYPES = frozenset(
    {
        "raw_conversation",
        "model_claim",
        "verification_result",
        "tool_result",
        "test_result",
        "user_confirmation",
        "governed_memory",
        "library_ref",
    }
)
LEGACY_PROMOTABLE_EVIDENCE_SOURCE_TYPES = frozenset(
    {
        "tool_result",
        "test_result",
        "user_confirmation",
        "governed_memory",
        "library_ref",
    }
)
LEGACY_PROMOTION_KINDS = frozenset({"procedure", "knowledge", "warning"})
LEGACY_PROMOTION_TARGETS = frozenset(
    {
        "ego_instruction",
        "ego_procedure",
        "library_knowledge",
        "durable_warning",
        "tool_routing_heuristic",
    }
)
LEGACY_RISK_CLASSES = frozenset(
    {"low", "normal", "high", "privileged", "security_sensitive"}
)
LEGACY_PROMOTION_STATES = frozenset({"active", "invalidated"})
LEGACY_APPLY_STATUSES = frozenset(
    {"applied", "rejected", "already_applied"}
)


def _legacy_required(value: str, *, name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{name} must be non-empty")
    return normalized


@dataclass(frozen=True)
class ExperienceEvidence:
    evidence_ref: str
    source_type: str
    summary: str
    verified: bool = False

    def __post_init__(self) -> None:
        _legacy_required(self.evidence_ref, name="evidence_ref")
        _legacy_required(self.summary, name="summary")
        if self.source_type not in LEGACY_EVIDENCE_SOURCE_TYPES:
            raise ValueError(
                f"unsupported evidence source_type: {self.source_type}"
            )

    @property
    def is_promotable(self) -> bool:
        return (
            self.verified
            and self.source_type in LEGACY_PROMOTABLE_EVIDENCE_SOURCE_TYPES
        )


@dataclass(frozen=True)
class ExperienceEpisode:
    episode_id: str
    outcome: str
    summary: str
    evidence: tuple[ExperienceEvidence, ...]
    trigger_conditions: tuple[str, ...] = ()
    procedure_steps: tuple[str, ...] = ()
    request_id: str = ""
    engine_id: str = ""
    verification_status: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    schema_version: int = EXPERIENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _legacy_required(self.episode_id, name="episode_id")
        _legacy_required(self.summary, name="summary")
        if self.outcome not in {"success", "failure"}:
            raise ValueError(f"unsupported episode outcome: {self.outcome}")
        if not self.evidence:
            raise ValueError("experience episode must carry evidence")
        if self.schema_version <= 0:
            raise ValueError("schema_version must be positive")


@dataclass(frozen=True)
class LessonCandidate:
    candidate_id: str
    kind: str
    target: str
    title: str
    proposed_content: str
    source_episode_ids: tuple[str, ...]
    source_evidence: tuple[ExperienceEvidence, ...]
    trigger_conditions: tuple[str, ...]
    validation_tests: tuple[str, ...]
    success_count: int = 0
    failure_count: int = 0
    scope: str = "general"
    risk_class: str = "normal"
    version: str = "1"
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: int = EXPERIENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _legacy_required(self.candidate_id, name="candidate_id")
        _legacy_required(self.title, name="title")
        _legacy_required(self.proposed_content, name="proposed_content")
        _legacy_required(self.scope, name="scope")
        _legacy_required(self.version, name="version")
        if self.kind not in LEGACY_PROMOTION_KINDS:
            raise ValueError(f"unsupported promotion kind: {self.kind}")
        if self.target not in LEGACY_PROMOTION_TARGETS:
            raise ValueError(f"unsupported promotion target: {self.target}")
        if self.risk_class not in LEGACY_RISK_CLASSES:
            raise ValueError(f"unsupported risk_class: {self.risk_class}")
        if self.success_count < 0 or self.failure_count < 0:
            raise ValueError("candidate outcome counters must be non-negative")
        if self.schema_version <= 0:
            raise ValueError("schema_version must be positive")


@dataclass(frozen=True)
class ReplayCaseResult:
    test_id: str
    passed: bool
    evidence_refs: tuple[str, ...] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        _legacy_required(self.test_id, name="test_id")


@dataclass(frozen=True)
class ReplayReport:
    candidate_id: str
    results: tuple[ReplayCaseResult, ...]
    run_id: str = field(
        default_factory=lambda: f"replay-{uuid.uuid4().hex[:12]}"
    )
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        _legacy_required(self.candidate_id, name="candidate_id")
        _legacy_required(self.run_id, name="run_id")


@dataclass(frozen=True)
class PromotionDecision:
    accepted: bool
    reason: str
    risk_flags: tuple[str, ...] = ()
    missing_tests: tuple[str, ...] = ()
    failed_tests: tuple[str, ...] = ()


@dataclass
class PromotionArtifact:
    artifact_id: str
    candidate_id: str
    kind: str
    target: str
    title: str
    content: str
    version: str
    source_episode_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    validation_run_id: str
    trigger_conditions: tuple[str, ...] = ()
    scope: str = "general"
    risk_class: str = "normal"
    created_at: float = field(default_factory=time.time)
    state: str = "active"
    invalidated_at: float | None = None
    invalidation_reason: str | None = None
    schema_version: int = EXPERIENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _legacy_required(self.artifact_id, name="artifact_id")
        _legacy_required(self.candidate_id, name="candidate_id")
        _legacy_required(self.title, name="title")
        _legacy_required(self.content, name="content")
        _legacy_required(self.version, name="version")
        _legacy_required(self.validation_run_id, name="validation_run_id")
        _legacy_required(self.scope, name="scope")
        if self.risk_class not in LEGACY_RISK_CLASSES:
            raise ValueError(f"unsupported risk_class: {self.risk_class}")
        if self.state not in LEGACY_PROMOTION_STATES:
            raise ValueError(f"unsupported promotion state: {self.state}")

    @property
    def active(self) -> bool:
        return self.state == "active"

    def invalidate(self, reason: str) -> None:
        if not self.active:
            raise ValueError("promotion artifact is already invalidated")
        self.state = "invalidated"
        self.invalidated_at = time.time()
        self.invalidation_reason = _legacy_required(reason, name="reason")


@dataclass(frozen=True)
class PromotionApplyRequest:
    artifact_id: str
    target_ref: str
    actor: str
    approval_ref: str
    reason: str

    def __post_init__(self) -> None:
        _legacy_required(self.artifact_id, name="artifact_id")
        _legacy_required(self.target_ref, name="target_ref")
        _legacy_required(self.actor, name="actor")
        _legacy_required(self.approval_ref, name="approval_ref")
        _legacy_required(self.reason, name="reason")


@dataclass(frozen=True)
class PromotionApplyReceipt:
    apply_id: str
    artifact_id: str
    target: str
    target_ref: str
    actor: str
    approval_ref: str
    reason: str
    status: str
    result_ref: str
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        _legacy_required(self.apply_id, name="apply_id")
        _legacy_required(self.artifact_id, name="artifact_id")
        _legacy_required(self.target, name="target")
        _legacy_required(self.target_ref, name="target_ref")
        _legacy_required(self.actor, name="actor")
        _legacy_required(self.approval_ref, name="approval_ref")
        _legacy_required(self.reason, name="reason")
        _legacy_required(self.result_ref, name="result_ref")
        if self.status not in LEGACY_APPLY_STATUSES:
            raise ValueError(f"unsupported apply status: {self.status}")


@dataclass(frozen=True)
class EgoInstructionPatch:
    patch_id: str
    artifact_id: str
    ego_id: str
    target: str
    instruction: str
    version: str
    evidence_refs: tuple[str, ...]
    approval_ref: str


@dataclass(frozen=True)
class PromotionOutcome:
    decision: PromotionDecision
    artifact: PromotionArtifact | None = None
