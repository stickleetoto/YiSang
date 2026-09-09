from __future__ import annotations

import json
from typing import Any, Iterator
from urllib import error as urllib_error
from urllib import request as urllib_request


class UpstreamHTTPError(RuntimeError):
    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"upstream HTTP {status}: {body[:500]}")
        self.status = status
        self.body = body


class OpenAIChatUpstream:
    """Small stdlib-only client for an OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url is required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    @property
    def chat_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = self._request(payload)
        try:
            with urllib_request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise UpstreamHTTPError(exc.code, body) from exc

        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("upstream returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise ValueError("upstream response must be a JSON object")
        return result

    def stream(self, payload: dict[str, Any]) -> Iterator[bytes]:
        request = self._request(payload)
        try:
            response = urllib_request.urlopen(request, timeout=self.timeout)
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise UpstreamHTTPError(exc.code, body) from exc

        try:
            while True:
                line = response.readline()
                if not line:
                    break
                yield line
        finally:
            response.close()

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
