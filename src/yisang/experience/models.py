from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import time
import uuid

EXPERIENCE_SCHEMA_VERSION = 1

EPISODE_OUTCOMES = frozenset({"success", "failure"})
EVIDENCE_SOURCE_TYPES = frozenset(
    {
        "raw_conversation",
        "model_claim",
        "tool_result",
        "test_result",
        "user_confirmation",
        "governed_memory",
        "library_ref",
    }
)
PROMOTABLE_EVIDENCE_SOURCE_TYPES = frozenset(
    {
        "tool_result",
        "test_result",
        "user_confirmation",
        "governed_memory",
        "library_ref",
    }
)
PROMOTION_KINDS = frozenset({"procedure", "knowledge", "warning"})
PROMOTION_TARGETS = frozenset(
    {
        "ego_instruction",
        "ego_procedure",
        "library_knowledge",
        "durable_warning",
        "tool_routing_heuristic",
    }
)
RISK_CLASSES = frozenset(
    {"low", "normal", "high", "privileged", "security_sensitive"}
)
PROMOTION_STATES = frozenset({"active", "invalidated"})
APPLY_STATUSES = frozenset({"applied", "rejected", "already_applied"})


def _required(value: str, *, name: str) -> str:
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
        _required(self.evidence_ref, name="evidence_ref")
        _required(self.summary, name="summary")
        if self.source_type not in EVIDENCE_SOURCE_TYPES:
            raise ValueError(f"unsupported evidence source_type: {self.source_type}")

    @property
    def is_promotable(self) -> bool:
        return self.verified and self.source_type in PROMOTABLE_EVIDENCE_SOURCE_TYPES


@dataclass(frozen=True)
class ExperienceEpisode:
    """Normalized experience evidence.

    Raw transcripts may be referenced as evidence, but this model deliberately
    stores a compact summary and structured outcome instead of making raw
    conversation text the durable promotion payload.
    """

    episode_id: str
    outcome: str
    summary: str
    evidence: tuple[ExperienceEvidence, ...]
    trigger_conditions: tuple[str, ...] = ()
    procedure_steps: tuple[str, ...] = ()
    created_at: float = field(default_factory=time.time)
    schema_version: int = EXPERIENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required(self.episode_id, name="episode_id")
        _required(self.summary, name="summary")
        if self.outcome not in EPISODE_OUTCOMES:
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
        _required(self.candidate_id, name="candidate_id")
        _required(self.title, name="title")
        _required(self.proposed_content, name="proposed_content")
        _required(self.scope, name="scope")
        _required(self.version, name="version")
        if self.kind not in PROMOTION_KINDS:
            raise ValueError(f"unsupported promotion kind: {self.kind}")
        if self.target not in PROMOTION_TARGETS:
            raise ValueError(f"unsupported promotion target: {self.target}")
        if self.risk_class not in RISK_CLASSES:
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
        _required(self.test_id, name="test_id")


@dataclass(frozen=True)
class ReplayReport:
    candidate_id: str
    results: tuple[ReplayCaseResult, ...]
    run_id: str = field(default_factory=lambda: f"replay-{uuid.uuid4().hex[:12]}")
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        _required(self.candidate_id, name="candidate_id")
        _required(self.run_id, name="run_id")


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
        _required(self.artifact_id, name="artifact_id")
        _required(self.candidate_id, name="candidate_id")
        _required(self.title, name="title")
        _required(self.content, name="content")
        _required(self.version, name="version")
        _required(self.validation_run_id, name="validation_run_id")
        _required(self.scope, name="scope")
        if self.risk_class not in RISK_CLASSES:
            raise ValueError(f"unsupported risk_class: {self.risk_class}")
        if self.state not in PROMOTION_STATES:
            raise ValueError(f"unsupported promotion state: {self.state}")

    @property
    def active(self) -> bool:
        return self.state == "active"

    def invalidate(self, reason: str) -> None:
        if not self.active:
            raise ValueError("promotion artifact is already invalidated")
        normalized = _required(reason, name="reason")
        self.state = "invalidated"
        self.invalidated_at = time.time()
        self.invalidation_reason = normalized


@dataclass(frozen=True)
class PromotionApplyRequest:
    artifact_id: str
    target_ref: str
    actor: str
    approval_ref: str
    reason: str

    def __post_init__(self) -> None:
        _required(self.artifact_id, name="artifact_id")
        _required(self.target_ref, name="target_ref")
        _required(self.actor, name="actor")
        _required(self.approval_ref, name="approval_ref")
        _required(self.reason, name="reason")


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
        _required(self.apply_id, name="apply_id")
        _required(self.artifact_id, name="artifact_id")
        _required(self.target, name="target")
        _required(self.target_ref, name="target_ref")
        _required(self.actor, name="actor")
        _required(self.approval_ref, name="approval_ref")
        _required(self.reason, name="reason")
        _required(self.result_ref, name="result_ref")
        if self.status not in APPLY_STATUSES:
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

    def __post_init__(self) -> None:
        _required(self.patch_id, name="patch_id")
        _required(self.artifact_id, name="artifact_id")
        _required(self.ego_id, name="ego_id")
        _required(self.instruction, name="instruction")
        _required(self.version, name="version")
        _required(self.approval_ref, name="approval_ref")


@dataclass(frozen=True)
class PromotionOutcome:
    decision: PromotionDecision
    artifact: PromotionArtifact | None = None
