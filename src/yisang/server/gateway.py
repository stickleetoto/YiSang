from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

from yisang.context.compiler import ContextCompiler
from yisang.core.models import YiSangRequest
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.router import EngineRouter
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.port import MemoryPort

from .protocol import (
    ProtocolError,
    last_user_text,
    normalize_tools,
    parse_chat_messages,
    parse_responses_messages,
    render_messages,
    require_model,
)


@dataclass(frozen=True)
class GatewayResult:
    text: str
    actions: list[Any]
    usage: dict[str, Any]
    upstream_model: str | None


class YiSangModelGateway:
    """Expose YiSang + a replaceable engine as a model-compatible backend.

    In delegated-tool mode, client tools are never executed by YiSang. They are
    presented to the attached engine as capabilities and any requested tool call
    is returned to the client (for example Codex) to execute.
    """

    def __init__(
        self,
        *,
        model_id: str,
        identity: IdentityCharter,
        state: AgentState,
        memory: MemoryPort,
        ego_registry: EgoRegistry,
        capability_router: CapabilityRouter,
        context_compiler: ContextCompiler,
        engine_router: EngineRouter,
    ) -> None:
        if not model_id.strip():
            raise ValueError("model_id is required")
        self.model_id = model_id
        self.identity = identity
        self.state = state
        self.memory = memory
        self.ego_registry = ego_registry
        self.capability_router = capability_router
        self.context_compiler = context_compiler
        self.engine_router = engine_router

    def models(self) -> dict[str, Any]:
        return {
            "object": "list",
            "data": [{
                "id": self.model_id,
                "object": "model",
                "created": 0,
                "owned_by": "yisang",
            }],
        }

    def chat_completions(self, payload: dict[str, Any]) -> dict[str, Any]:
        require_model(payload, self.model_id)
        if payload.get("stream") is True:
            raise ProtocolError(
                "streaming is not implemented yet",
                code="streaming_not_supported",
                param="stream",
            )
        messages = parse_chat_messages(payload)
        tools = normalize_tools(payload, responses=False)
        result = self._run(messages=messages, tools=tools)

        message: dict[str, Any] = {
            "role": "assistant",
            "content": result.text or None,
        }
        finish_reason = "stop"
        if result.actions:
            message["tool_calls"] = [self._chat_tool_call(action) for action in result.actions]
            finish_reason = "tool_calls"

        return {
            "id": f"chatcmpl_{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.model_id,
            "choices": [{
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }],
            "usage": _chat_usage(result.usage),
            "yisang": {
                "upstream_model": result.upstream_model,
                "delegated_tools": True,
            },
        }

    def responses(self, payload: dict[str, Any]) -> dict[str, Any]:
        require_model(payload, self.model_id)
        if payload.get("stream") is True:
            raise ProtocolError(
                "streaming is not implemented yet",
                code="streaming_not_supported",
                param="stream",
            )
        messages = parse_responses_messages(payload)
        tools = normalize_tools(payload, responses=True)
        result = self._run(messages=messages, tools=tools)

        output: list[dict[str, Any]] = []
        if result.text:
            output.append({
                "id": f"msg_{uuid.uuid4().hex}",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{
                    "type": "output_text",
                    "text": result.text,
                    "annotations": [],
                }],
            })
        for action in result.actions:
            call_id = f"call_{uuid.uuid4().hex}"
            output.append({
                "id": f"fc_{uuid.uuid4().hex}",
                "type": "function_call",
                "status": "completed",
                "call_id": call_id,
                "name": action.action,
                "arguments": json.dumps(action.arguments, ensure_ascii=False, separators=(",", ":")),
            })

        return {
            "id": f"resp_{uuid.uuid4().hex}",
            "object": "response",
            "created_at": int(time.time()),
            "status": "completed",
            "model": self.model_id,
            "output": output,
            "output_text": result.text,
            "parallel_tool_calls": bool(payload.get("parallel_tool_calls", True)),
            "tools": payload.get("tools", []),
            "usage": _responses_usage(result.usage),
            "error": None,
            "incomplete_details": None,
            "metadata": payload.get("metadata", {}),
            "yisang": {
                "upstream_model": result.upstream_model,
                "delegated_tools": True,
            },
        }

    def _run(self, *, messages: list[dict[str, str]], tools: list[dict[str, Any]]) -> GatewayResult:
        query = last_user_text(messages)
        memories = self.memory.search(query, limit=8)
        egos = self.capability_router.route(
            query,
            self.ego_registry.list_all(),
            limit=3,
        )
        request = YiSangRequest(
            request_id=f"model-{uuid.uuid4().hex}",
            text=render_messages(messages),
            metadata={"mode": "model_server", "delegated_tools": True},
        )
        context = self.context_compiler.compile(
            request=request,
            identity=self.identity,
            state=self.state,
            memories=memories,
            egos=egos,
            tools=tools,
        )
        engine = self.engine_router.get(self.state.active_engine)
        engine_result = engine.generate(context)
        usage = engine_result.metadata.get("usage", {})
        if not isinstance(usage, dict):
            usage = {}
        upstream_model = engine_result.metadata.get("model")
        if upstream_model is not None:
            upstream_model = str(upstream_model)
        return GatewayResult(
            text=engine_result.text,
            actions=list(engine_result.action_proposals),
            usage=usage,
            upstream_model=upstream_model,
        )

    @staticmethod
    def _chat_tool_call(action) -> dict[str, Any]:
        return {
            "id": f"call_{uuid.uuid4().hex}",
            "type": "function",
            "function": {
                "name": action.action,
                "arguments": json.dumps(action.arguments, ensure_ascii=False, separators=(",", ":")),
            },
        }


def _chat_usage(usage: dict[str, Any]) -> dict[str, int]:
    prompt = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
    completion = int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": int(usage.get("total_tokens", prompt + completion) or (prompt + completion)),
    }


def _responses_usage(usage: dict[str, Any]) -> dict[str, int]:
    input_tokens = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)) or 0)
    output_tokens = int(usage.get("output_tokens", usage.get("completion_tokens", 0)) or 0)
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": int(usage.get("total_tokens", input_tokens + output_tokens) or (input_tokens + output_tokens)),
    }
