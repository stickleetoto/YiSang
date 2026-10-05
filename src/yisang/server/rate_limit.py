from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class RateLimitSnapshot:
    min_interval: float
    blocked_for: float
    next_start_in: float
    consecutive_rate_limits: int
    consecutive_transient_failures: int
    blocked_status: int | None
    blocked_reason: str | None

    def to_dict(self) -> dict[str, float | int | str | None]:
        return {
            "min_interval": self.min_interval,
            "blocked_for": self.blocked_for,
            "next_start_in": self.next_start_in,
            "consecutive_rate_limits": self.consecutive_rate_limits,
            "consecutive_transient_failures": self.consecutive_transient_failures,
            "blocked_status": self.blocked_status,
            "blocked_reason": self.blocked_reason,
        }


class LocalUpstreamCooldownError(RuntimeError):
    def __init__(self, status: int, retry_after: float, reason: str) -> None:
        retry_after = max(0.0, float(retry_after))
        super().__init__(
            f"upstream request suppressed by local {reason} cooldown; "
            f"retry after {max(1, math.ceil(retry_after))}s"
        )
        self.status = int(status)
        self.retry_after = retry_after
        self.reason = reason


class LocalRateLimitError(LocalUpstreamCooldownError):
    def __init__(self, retry_after: float) -> None:
        super().__init__(429, retry_after, "rate-limit")


class RateLimitGovernor:
    """Contain provider bursts, rate limits, and transient service failures.

    YiSang never retries a failed provider request itself. The governor only
    spaces provider request starts, opens exponential cooldowns after HTTP 429
    or transient 5xx/transport failures, rejects requests locally during an
    active cooldown, and resets strike counters after a successful response.
    """

    def __init__(
        self,
        *,
        min_interval: float = 2.0,
        backoff_initial: float = 2.0,
        backoff_max: float = 60.0,
        transient_backoff_initial: float = 2.0,
        transient_backoff_max: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if min_interval < 0:
            raise ValueError("min_interval must be non-negative")
        if backoff_initial <= 0:
            raise ValueError("backoff_initial must be positive")
        if backoff_max < backoff_initial:
            raise ValueError("backoff_max must be >= backoff_initial")
        if transient_backoff_initial <= 0:
            raise ValueError("transient_backoff_initial must be positive")
        if transient_backoff_max < transient_backoff_initial:
            raise ValueError(
                "transient_backoff_max must be >= transient_backoff_initial"
            )

        self.min_interval = float(min_interval)
        self.backoff_initial = float(backoff_initial)
        self.backoff_max = float(backoff_max)
        self.transient_backoff_initial = float(transient_backoff_initial)
        self.transient_backoff_max = float(transient_backoff_max)
        self._clock = clock
        self._sleeper = sleeper
        self._lock = threading.Lock()
        self._next_start_at = 0.0
        self._blocked_until = 0.0
        self._blocked_status: int | None = None
        self._blocked_reason: str | None = None
        self._consecutive_rate_limits = 0
        self._consecutive_transient_failures = 0

    def before_request(self) -> None:
        """Wait for spacing, then fail locally if a cooldown is active."""

        with self._lock:
            now = self._clock()
            self._raise_if_blocked(now)

            scheduled = max(now, self._next_start_at)
            wait_for = max(0.0, scheduled - now)
            self._next_start_at = scheduled + self.min_interval

        if wait_for > 0:
            self._sleeper(wait_for)

        with self._lock:
            self._raise_if_blocked(self._clock())

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_rate_limits = 0
            self._consecutive_transient_failures = 0
            self._blocked_until = 0.0
            self._blocked_status = None
            self._blocked_reason = None

    def record_rate_limit(self, retry_after: float | None = None) -> float:
        with self._lock:
            now = self._clock()
            self._consecutive_rate_limits += 1
            self._consecutive_transient_failures = 0
            exponential = min(
                self.backoff_max,
                self.backoff_initial
                * (2 ** max(0, self._consecutive_rate_limits - 1)),
            )
            return self._open_cooldown(
                now=now,
                delay=max(exponential, max(0.0, float(retry_after or 0.0))),
                status=429,
                reason="rate-limit",
            )

    def record_transient_failure(self, retry_after: float | None = None) -> float:
        with self._lock:
            now = self._clock()
            self._consecutive_transient_failures += 1
            self._consecutive_rate_limits = 0
            exponential = min(
                self.transient_backoff_max,
                self.transient_backoff_initial
                * (2 ** max(0, self._consecutive_transient_failures - 1)),
            )
            return self._open_cooldown(
                now=now,
                delay=max(exponential, max(0.0, float(retry_after or 0.0))),
                status=503,
                reason="transient-upstream",
            )

    def remaining_cooldown(self) -> float:
        with self._lock:
            return max(0.0, self._blocked_until - self._clock())

    def snapshot(self) -> RateLimitSnapshot:
        with self._lock:
            now = self._clock()
            blocked_for = max(0.0, self._blocked_until - now)
            return RateLimitSnapshot(
                min_interval=self.min_interval,
                blocked_for=blocked_for,
                next_start_in=max(0.0, self._next_start_at - now),
                consecutive_rate_limits=self._consecutive_rate_limits,
                consecutive_transient_failures=self._consecutive_transient_failures,
                blocked_status=self._blocked_status if blocked_for > 0 else None,
                blocked_reason=self._blocked_reason if blocked_for > 0 else None,
            )

    def _open_cooldown(
        self,
        *,
        now: float,
        delay: float,
        status: int,
        reason: str,
    ) -> float:
        self._blocked_until = max(self._blocked_until, now + delay)
        self._blocked_status = status
        self._blocked_reason = reason
        self._next_start_at = max(
            self._next_start_at,
            self._blocked_until + self.min_interval,
        )
        return max(0.0, self._blocked_until - now)

    def _raise_if_blocked(self, now: float) -> None:
        blocked_for = self._blocked_until - now
        if blocked_for <= 0:
            return
        status = self._blocked_status or 503
        reason = self._blocked_reason or "upstream"
        if status == 429:
            raise LocalRateLimitError(blocked_for)
        raise LocalUpstreamCooldownError(status, blocked_for, reason)
