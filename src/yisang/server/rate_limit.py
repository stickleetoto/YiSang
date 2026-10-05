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

    def to_dict(self) -> dict[str, float | int]:
        return {
            "min_interval": self.min_interval,
            "blocked_for": self.blocked_for,
            "next_start_in": self.next_start_in,
            "consecutive_rate_limits": self.consecutive_rate_limits,
        }


class LocalRateLimitError(RuntimeError):
    def __init__(self, retry_after: float) -> None:
        retry_after = max(0.0, float(retry_after))
        super().__init__(
            f"upstream request suppressed by local cooldown; retry after "
            f"{max(1, math.ceil(retry_after))}s"
        )
        self.retry_after = retry_after


class RateLimitGovernor:
    """Serialize provider request starts and contain repeated upstream 429s.

    The governor never retries a provider call itself. It only spaces request
    starts, records provider 429s, opens an exponential local cooldown, rejects
    requests locally while that cooldown is open, and resets the strike count
    after a successful provider response.
    """

    def __init__(
        self,
        *,
        min_interval: float = 2.0,
        backoff_initial: float = 2.0,
        backoff_max: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if min_interval < 0:
            raise ValueError("min_interval must be non-negative")
        if backoff_initial <= 0:
            raise ValueError("backoff_initial must be positive")
        if backoff_max < backoff_initial:
            raise ValueError("backoff_max must be >= backoff_initial")

        self.min_interval = float(min_interval)
        self.backoff_initial = float(backoff_initial)
        self.backoff_max = float(backoff_max)
        self._clock = clock
        self._sleeper = sleeper
        self._lock = threading.Lock()
        self._next_start_at = 0.0
        self._blocked_until = 0.0
        self._consecutive_rate_limits = 0

    def before_request(self) -> None:
        """Wait for spacing, then fail locally if a cooldown is active."""

        with self._lock:
            now = self._clock()
            blocked_for = self._blocked_until - now
            if blocked_for > 0:
                raise LocalRateLimitError(blocked_for)

            scheduled = max(now, self._next_start_at)
            wait_for = max(0.0, scheduled - now)
            self._next_start_at = scheduled + self.min_interval

        if wait_for > 0:
            self._sleeper(wait_for)

        # Another request may have received 429 while this one was waiting.
        with self._lock:
            now = self._clock()
            blocked_for = self._blocked_until - now
            if blocked_for > 0:
                raise LocalRateLimitError(blocked_for)

    def record_success(self) -> None:
        with self._lock:
            self._consecutive_rate_limits = 0

    def record_rate_limit(self, retry_after: float | None = None) -> float:
        """Open or extend cooldown and return the effective retry delay."""

        with self._lock:
            now = self._clock()
            self._consecutive_rate_limits += 1
            exponential = min(
                self.backoff_max,
                self.backoff_initial
                * (2 ** max(0, self._consecutive_rate_limits - 1)),
            )
            provider_delay = max(0.0, float(retry_after or 0.0))
            delay = max(exponential, provider_delay)
            self._blocked_until = max(self._blocked_until, now + delay)
            self._next_start_at = max(
                self._next_start_at,
                self._blocked_until + self.min_interval,
            )
            return max(0.0, self._blocked_until - now)

    def remaining_cooldown(self) -> float:
        with self._lock:
            return max(0.0, self._blocked_until - self._clock())

    def snapshot(self) -> RateLimitSnapshot:
        with self._lock:
            now = self._clock()
            return RateLimitSnapshot(
                min_interval=self.min_interval,
                blocked_for=max(0.0, self._blocked_until - now),
                next_start_in=max(0.0, self._next_start_at - now),
                consecutive_rate_limits=self._consecutive_rate_limits,
            )
