from __future__ import annotations

import json
from threading import Thread
from urllib import error as urllib_error
from urllib import request as urllib_request

from yisang.context.compiler import ContextCompiler
from yisang.ego.registry import EgoRegistry
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.server.http import create_http_server
from yisang.server.proxy import YiSangModelProxy
from yisang.server.upstream import UpstreamHTTPError


class FakeUpstream:
    def __init__(self):
        self.seen = []

    def complete(self, payload):
        self.seen.append(payload)
        return {
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "model": payload["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
        }

    def stream(self, payload):
        self.seen.append(payload)
        yield b'data: {"id":"c1","model":"qwen","choices":[{"index":0,"delta":{"content":"o"}}]}\n\n'
        yield b"data: [DONE]\n\n"


class FailingStreamUpstream(FakeUpstream):
    def stream(self, payload):
        raise UpstreamHTTPError(503, "model unavailable")
        yield b""  # pragma: no cover


def _server(upstream=None):
    proxy = YiSangModelProxy(
        model_id="yisang-qwen",
        upstream_model="qwen",
        identity=IdentityCharter("yisang-model", "YiSang"),
        state=AgentState(active_engine="qwen"),
        memory=InMemoryMemoryPort(),
        ego_registry=EgoRegistry(),
        context_compiler=ContextCompiler(),
    )
    upstream = upstream or FakeUpstream()
    server = create_http_server(
        host="127.0.0.1",
        port=0,
        proxy=proxy,
        upstream=upstream,  # type: ignore[arg-type]
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, upstream


def _url(server, path):
    return f"http://127.0.0.1:{server.server_port}{path}"


def test_models_and_chat_completion_endpoints():
    server, thread, upstream = _server()
    try:
        with urllib_request.urlopen(_url(server, "/v1/models/")) as response:
            models = json.loads(response.read())
        assert models["data"][0]["id"] == "yisang-qwen"

        request = urllib_request.Request(
            _url(server, "/v1/chat/completions"),
            data=json.dumps(
                {
                    "model": "yisang-qwen",
                    "messages": [{"role": "user", "content": "hello"}],
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(request) as response:
            result = json.loads(response.read())

        assert result["model"] == "yisang-qwen"
        assert result["choices"][0]["message"]["content"] == "ok"
        assert upstream.seen[0]["model"] == "qwen"
        assert upstream.seen[0]["messages"][0]["role"] == "system"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_stream_passthrough_rewrites_model():
    server, thread, _ = _server()
    try:
        request = urllib_request.Request(
            _url(server, "/v1/chat/completions"),
            data=json.dumps(
                {
                    "model": "yisang-qwen",
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": True,
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(request) as response:
            text = response.read().decode()
        assert '"model":"yisang-qwen"' in text
        assert "data: [DONE]" in text
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_stream_upstream_failure_is_clean_502_before_sse_headers():
    server, thread, _ = _server(FailingStreamUpstream())
    try:
        request = urllib_request.Request(
            _url(server, "/v1/chat/completions"),
            data=json.dumps(
                {
                    "model": "yisang-qwen",
                    "messages": [{"role": "user", "content": "hello"}],
                    "stream": True,
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib_request.urlopen(request)
        except urllib_error.HTTPError as exc:
            body = json.loads(exc.read())
            assert exc.code == 502
            assert body["error"]["type"] == "upstream_error"
        else:
            raise AssertionError("failing upstream unexpectedly returned 200")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_responses_endpoint_fails_with_actionable_error():
    server, thread, _ = _server()
    try:
        request = urllib_request.Request(
            _url(server, "/v1/responses/"),
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib_request.urlopen(request)
        except urllib_error.HTTPError as exc:
            body = json.loads(exc.read())
            assert exc.code == 501
            assert "wire_api" in body["error"]["message"]
        else:
            raise AssertionError("responses endpoint unexpectedly succeeded")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
