from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import socket
from typing import Any, Iterator
from urllib import error as urllib_error
from urllib import request as urllib_request

from .rate_limit import LocalUpstreamCooldownError, RateLimitGovernor


class UpstreamHTTPError(RuntimeError):
    def __init__(
        self,
        status: int,
        body: str,
        *,
        retry_after: float | None = None,
        locally_blocked: bool = False,
    ) -> None:
        super().__init__(f"upstream HTTP {status}: {body[:500]}")
        self.status = status
        self.body = body
        self.retry_after = retry_after
        self.locally_blocked = locally_blocked


def retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None

    try:
        seconds = float(text)
    except ValueError:
        seconds = None
    if seconds is not None:
        return max(0.0, seconds)

    try:
        target = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return max(0.0, (target - now).total_seconds())


class OpenAIChatUpstream:
    """Small stdlib-only client for an OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 120.0,
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
    def chat_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._before_request()
        request = self._request(payload)
        try:
            with urllib_request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib_error.HTTPError as exc:
            self._raise_http_error(exc)
        except (urllib_error.URLError, TimeoutError, socket.timeout, OSError) as exc:
            self._raise_transport_error(exc)
        self._record_success()

        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("upstream returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise ValueError("upstream response must be a JSON object")
        return result

    def stream(self, payload: dict[str, Any]) -> Iterator[bytes]:
        self._before_request()
        request = self._request(payload)
        try:
            response = urllib_request.urlopen(request, timeout=self.timeout)
        except urllib_error.HTTPError as exc:
            self._raise_http_error(exc)
        except (urllib_error.URLError, TimeoutError, socket.timeout, OSError) as exc:
            self._raise_transport_error(exc)
        self._record_success()

        try:
            while True:
                line = response.readline()
                if not line:
                    break
                yield line
        finally:
            response.close()

    def _before_request(self) -> None:
        if self.rate_limit_governor is None:
            return
        try:
            self.rate_limit_governor.before_request()
        except LocalUpstreamCooldownError as exc:
            raise UpstreamHTTPError(
                exc.status,
                str(exc),
                retry_after=exc.retry_after,
                locally_blocked=True,
            ) from exc

    def _record_success(self) -> None:
        if self.rate_limit_governor is not None:
            self.rate_limit_governor.record_success()

    def _raise_http_error(self, exc: urllib_error.HTTPError) -> None:
        body = exc.read().decode("utf-8", errors="replace")
        retry_after = retry_after_seconds(
            exc.headers.get("Retry-After") if exc.headers is not None else None
        )
        if self.rate_limit_governor is not None:
            if exc.code == 429:
                retry_after = self.rate_limit_governor.record_rate_limit(retry_after)
            elif 500 <= exc.code <= 599:
                retry_after = self.rate_limit_governor.record_transient_failure(
                    retry_after
                )
        raise UpstreamHTTPError(
            exc.code,
            body,
            retry_after=retry_after,
        ) from exc

    def _raise_transport_error(self, exc: BaseException) -> None:
        retry_after = None
        if self.rate_limit_governor is not None:
            retry_after = self.rate_limit_governor.record_transient_failure()
        raise UpstreamHTTPError(
            503,
            f"transport error: {type(exc).__name__}: {exc}",
            retry_after=retry_after,
        ) from exc

    def _request(self, payload: dict[str, Any]) -> urllib_request.Request:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream" if payload.get("stream") else "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return urllib_request.Request(
            self.chat_url,
            data=body,
            headers=headers,
            method="POST",
        )
