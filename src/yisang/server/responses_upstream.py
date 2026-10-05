from __future__ import annotations

import json
import socket
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from .rate_limit import LocalUpstreamCooldownError, RateLimitGovernor
from .upstream import UpstreamHTTPError, retry_after_seconds


class OpenAIResponsesUpstream:
    """Small stdlib-only client for an OpenAI-compatible Responses endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 1800.0,
        rate_limit_governor: RateLimitGovernor | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url is required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.rate_limit_governor = rate_limit_governor

    @property
    def responses_url(self) -> str:
        return f"{self.base_url}/responses"

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.rate_limit_governor is not None:
            try:
                self.rate_limit_governor.before_request()
            except LocalUpstreamCooldownError as exc:
                raise UpstreamHTTPError(
                    exc.status,
                    str(exc),
                    retry_after=exc.retry_after,
                    locally_blocked=True,
                ) from exc

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib_request.Request(
            self.responses_url,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib_error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            retry_after = retry_after_seconds(
                exc.headers.get("Retry-After") if exc.headers is not None else None
            )
            if self.rate_limit_governor is not None:
                if exc.code == 429:
                    retry_after = self.rate_limit_governor.record_rate_limit(
                        retry_after
                    )
                elif 500 <= exc.code <= 599:
                    retry_after = (
                        self.rate_limit_governor.record_transient_failure(
                            retry_after
                        )
                    )
            raise UpstreamHTTPError(
                exc.code,
                error_body,
                retry_after=retry_after,
            ) from exc
        except (urllib_error.URLError, TimeoutError, socket.timeout, OSError) as exc:
            retry_after = None
            if self.rate_limit_governor is not None:
                retry_after = self.rate_limit_governor.record_transient_failure()
            raise UpstreamHTTPError(
                503,
                f"transport error: {type(exc).__name__}: {exc}",
                retry_after=retry_after,
            ) from exc

        if self.rate_limit_governor is not None:
            self.rate_limit_governor.record_success()

        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("upstream returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise ValueError("upstream response must be a JSON object")
        return result
