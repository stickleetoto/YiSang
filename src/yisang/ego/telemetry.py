from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import time


EGO_TELEMETRY_KINDS = frozenset({"runtime_use", "replay_health"})


@dataclass(frozen=True)
class EgoTelemetryEvent:
    event_id: str
    kind: str
    ego_id: str
    version: str
    success: bool
    request_ref: str
    verification_status: str = ""
    latency_ms: float | None = None
    action_failure_count: int = 0
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id must be non-empty")
        if self.kind not in EGO_TELEMETRY_KINDS:
            raise ValueError(f"unsupported E.G.O telemetry kind: {self.kind}")
        if not self.ego_id.strip():
            raise ValueError("ego_id must be non-empty")
        if not self.version.strip():
            raise ValueError("version must be non-empty")
        if not self.request_ref.strip():
            raise ValueError("request_ref must be non-empty")
        if self.latency_ms is not None and self.latency_ms < 0:
            raise ValueError("latency_ms must be non-negative")
        if self.action_failure_count < 0:
            raise ValueError("action_failure_count must be non-negative")

    @classmethod
    def runtime_use(
        cls,
        *,
        ego_id: str,
        version: str,
        request_id: str,
        success: bool,
        verification_status: str,
        latency_ms: float,
        action_failure_count: int,
        created_at: float | None = None,
    ) -> "EgoTelemetryEvent":
        timestamp = time.time() if created_at is None else float(created_at)
        return cls(
            event_id=_stable_event_id(
                "runtime_use", ego_id, version, request_id
            ),
            kind="runtime_use",
            ego_id=ego_id,
            version=version,
            success=success,
            request_ref=request_id,
            verification_status=verification_status,
            latency_ms=latency_ms,
            action_failure_count=action_failure_count,
            created_at=timestamp,
        )

    @classmethod
    def replay_health(
        cls,
        *,
        ego_id: str,
        version: str,
        replay_run_id: str,
        success: bool,
        created_at: float | None = None,
    ) -> "EgoTelemetryEvent":
        timestamp = time.time() if created_at is None else float(created_at)
        return cls(
            event_id=_stable_event_id(
                "replay_health", ego_id, version, replay_run_id
            ),
            kind="replay_health",
            ego_id=ego_id,
            version=version,
            success=success,
            request_ref=replay_run_id,
            verification_status="PASS" if success else "FAIL",
            created_at=timestamp,
        )


@dataclass(frozen=True)
class EgoTelemetrySummary:
    ego_id: str
    version: str
    sample_count: int
    runtime_successes: int
    runtime_failures: int
    replay_passes: int
    replay_failures: int
    weighted_success_rate: float
    routing_adjustment: float
    average_latency_ms: float | None


class EgoTelemetryPort(ABC):
    @abstractmethod
    def record(self, event: EgoTelemetryEvent) -> EgoTelemetryEvent:
        raise NotImplementedError

    @abstractmethod
    def events(
        self,
        *,
        ego_id: str | None = None,
        version: str | None = None,
    ) -> tuple[EgoTelemetryEvent, ...]:
        raise NotImplementedError


class EgoAdaptiveScorer:
    """Bounded, decayed feedback scorer for E.G.O routing.

    It never replaces semantic relevance. It emits only a small signed
    adjustment after a minimum number of observations.
    """

    def __init__(
        self,
        *,
        min_samples: int = 3,
        saturation_samples: int = 12,
        half_life_days: float = 30.0,
        replay_weight: float = 2.0,
        max_adjustment: float = 0.35,
        prior_strength: float = 2.0,
    ) -> None:
        if min_samples < 1:
            raise ValueError("min_samples must be positive")
        if saturation_samples < min_samples:
            raise ValueError(
                "saturation_samples must be >= min_samples"
            )
        if half_life_days <= 0:
            raise ValueError("half_life_days must be positive")
        if replay_weight <= 0:
            raise ValueError("replay_weight must be positive")
        if not 0 < max_adjustment <= 1:
            raise ValueError("max_adjustment must be in (0, 1]")
        if prior_strength < 0:
            raise ValueError("prior_strength must be non-negative")
        self.min_samples = min_samples
        self.saturation_samples = saturation_samples
        self.half_life_seconds = half_life_days * 86400.0
        self.replay_weight = replay_weight
        self.max_adjustment = max_adjustment
        self.prior_strength = prior_strength

    def summary(
        self,
        port: EgoTelemetryPort,
        *,
        ego_id: str,
        version: str,
        now: float | None = None,
    ) -> EgoTelemetrySummary:
        items = port.events(ego_id=ego_id, version=version)
        current = time.time() if now is None else float(now)
        weighted_success = 0.0
        total_weight = 0.0
        latencies: list[float] = []
        runtime_successes = runtime_failures = 0
        replay_passes = replay_failures = 0

        for event in items:
            age = max(0.0, current - event.created_at)
            decay = math.pow(0.5, age / self.half_life_seconds)
            kind_weight = (
                self.replay_weight
                if event.kind == "replay_health"
                else 1.0
            )
            weight = decay * kind_weight
            total_weight += weight
            if event.success:
                weighted_success += weight
            if event.kind == "runtime_use":
                if event.success:
                    runtime_successes += 1
                else:
                    runtime_failures += 1
                if event.latency_ms is not None:
                    latencies.append(event.latency_ms)
            elif event.success:
                replay_passes += 1
            else:
                replay_failures += 1

        sample_count = len(items)
        if total_weight == 0:
            rate = 0.5
        else:
            prior_success = self.prior_strength * 0.5
            rate = (
                weighted_success + prior_success
            ) / (total_weight + self.prior_strength)

        if sample_count < self.min_samples:
            adjustment = 0.0
        else:
            confidence = min(
                1.0,
                sample_count / float(self.saturation_samples),
            )
            centered = (rate - 0.5) * 2.0
            adjustment = max(
                -self.max_adjustment,
                min(
                    self.max_adjustment,
                    centered * self.max_adjustment * confidence,
                ),
            )

        return EgoTelemetrySummary(
            ego_id=ego_id,
            version=version,
            sample_count=sample_count,
            runtime_successes=runtime_successes,
            runtime_failures=runtime_failures,
            replay_passes=replay_passes,
            replay_failures=replay_failures,
            weighted_success_rate=rate,
            routing_adjustment=adjustment,
            average_latency_ms=(
                sum(latencies) / len(latencies)
                if latencies
                else None
            ),
        )


def _stable_event_id(
    kind: str,
    ego_id: str,
    version: str,
    request_ref: str,
) -> str:
    raw = json.dumps(
        [kind, ego_id, version, request_ref],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "ego-telemetry-" + sha256(raw.encode("utf-8")).hexdigest()[:16]
