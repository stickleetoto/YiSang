from __future__ import annotations

import json
from typing import Any, Callable
from urllib import request as urllib_request

from .base import LLMEngine, EngineResult
from .structured import StructuredActionDecoder
from yisang.context.render import render_context

Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


def _http_post_json(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(url, data=body, headers=headers, method="POST")
    with urllib_request.urlopen(req, timeout=timeout) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8"))


class OpenAICompatibleEngine(LLMEngine):
    """Connect YiSang to LM Studio or another OpenAI-compatible chat endpoint."""

    def __init__(
        self,
        *,
        engine_id: str,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 120.0,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        structured_actions: bool = True,
        action_decoder: StructuredActionDecoder | None = None,
        transport: Transport | None = None,
    ) -> None:
        if not engine_id.strip():
            raise ValueError("engine_id is required")
        if not model.strip():
            raise ValueError("model is required")
        if timeout <= 0:
            raise ValueError("timeout must be positive")

        self.engine_id = engine_id
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.structured_actions = structured_actions
        self._decoder = action_decoder or StructuredActionDecoder()
        self._transport = transport or _http_post_json

    @property
    def supports_action_feedback(self) -> bool:
        return self.structured_actions

    def generate(self, context) -> EngineResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a replaceable reasoning engine operating inside "
                        "the YiSang enhancement layer. Follow the provided identity, "
                        "memory, capability, tool and constraints. Tool requests are "
                        "proposals only; YiSang decides whether they execute."
                    ),
                },
                {"role": "user", "content": render_context(context)},
            ],
            "temperature": self.temperature,
        }
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        data = self._transport(
            f"{self.base_url}/chat/completions",
            headers,
            payload,
            self.timeout,
        )

        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("invalid OpenAI-compatible response shape") from exc

        if not isinstance(message, dict):
            raise ValueError("response message must be an object")

        if self.structured_actions:
            decoded = self._decoder.decode(
                message,
                requested_by=self.engine_id,
            )
            content = decoded.text
            action_proposals = decoded.actions
        else:
            content = message.get("content")
            if not isinstance(content, str):
                raise ValueError("response content must be a string")
            action_proposals = []

        return EngineResult(
            engine_id=self.engine_id,
            text=content,
            action_proposals=action_proposals,
            metadata={
                "model": data.get("model", self.model),
                "usage": data.get("usage", {}),
                "structured_actions": self.structured_actions,
            },
        )
