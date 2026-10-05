from __future__ import annotations

import json
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from .upstream import UpstreamHTTPError


class OpenAIResponsesUpstream:
    """Small stdlib-only client for an OpenAI-compatible Responses endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 1800.0,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url is required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    @property
    def responses_url(self) -> str:
        return f"{self.base_url}/responses"

    def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
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
            raise UpstreamHTTPError(exc.code, error_body) from exc

        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("upstream returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise ValueError("upstream response must be a JSON object")
        return result
