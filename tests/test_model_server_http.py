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


class ToolCallingUpstream(FakeUpstream):
    def complete(self, payload):
        self.seen.append(payload)
        if any(message.get("role") == "tool" for message in payload["messages"]):
            return {
                "id": "chatcmpl-2",
                "object": "chat.completion",
                "model": payload["model"],
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "done"},
                        "finish_reason": "stop",
                    }
                ],
            }
        return {
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "model": payload["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "exec_command",
                                    "arguments": '{"cmd":"Get-Content test.txt"}',
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
        }


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


def _post_json(server, path, payload):
    request = urllib_request.Request(
        _url(server, path),
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib_request.urlopen(request) as response:
        return response.status, response.headers, response.read()


def test_models_and_chat_completion_endpoints():
    server, thread, upstream = _server()
    try:
        with urllib_request.urlopen(_url(server, "/v1/models/")) as response:
            models = json.loads(response.read())
        assert models["data"][0]["id"] == "yisang-qwen"

        _, _, raw = _post_json(
            server,
            "/v1/chat/completions",
            {
                "model": "yisang-qwen",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        result = json.loads(raw)

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
        _, _, raw = _post_json(
            server,
            "/v1/chat/completions",
            {
                "model": "yisang-qwen",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            },
        )
        text = raw.decode()
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


def test_responses_endpoint_streams_codex_compatible_events():
    server, thread, upstream = _server()
    try:
        status, headers, raw = _post_json(
            server,
            "/v1/responses",
            {
                "model": "yisang-qwen",
                "instructions": "Follow the repository rules.",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "hello"}],
                    }
                ],
                "tools": [
                    {
                        "type": "function",
                        "name": "exec_command",
                        "description": "Run a shell command",
                        "parameters": {"type": "object"},
                    }
                ],
                "stream": True,
            },
        )
        text = raw.decode()

        assert status == 200
        assert headers["Content-Type"].startswith("text/event-stream")
        assert "event: response.created" in text
        assert "event: response.output_item.done" in text
        assert '"type":"output_text","text":"ok"' in text
        assert "event: response.completed" in text

        forwarded = upstream.seen[0]
        assert forwarded["model"] == "qwen"
        assert forwarded["stream"] is False
        assert forwarded["messages"][0]["role"] == "system"
        assert forwarded["messages"][1]["role"] == "system"
        assert forwarded["messages"][2]["role"] == "user"
        assert forwarded["tools"][0]["function"]["name"] == "exec_command"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_responses_tool_call_round_trip_back_to_codex():
    server, thread, upstream = _server(ToolCallingUpstream())
    try:
        common_tools = [
            {
                "type": "function",
                "name": "exec_command",
                "description": "Run a shell command",
                "parameters": {
                    "type": "object",
                    "properties": {"cmd": {"type": "string"}},
                    "required": ["cmd"],
                },
            }
        ]
        _, _, first_raw = _post_json(
            server,
            "/v1/responses",
            {
                "model": "yisang-qwen",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "read test.txt"}],
                    }
                ],
                "tools": common_tools,
                "stream": True,
            },
        )
        first_text = first_raw.decode()
        assert '"type":"function_call"' in first_text
        assert '"call_id":"call-1"' in first_text
        assert '"name":"exec_command"' in first_text

        _, _, second_raw = _post_json(
            server,
            "/v1/responses",
            {
                "model": "yisang-qwen",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "read test.txt"}],
                    },
                    {
                        "type": "function_call",
                        "call_id": "call-1",
                        "name": "exec_command",
                        "arguments": '{"cmd":"Get-Content test.txt"}',
                    },
                    {
                        "type": "function_call_output",
                        "call_id": "call-1",
                        "output": "hello",
                    },
                ],
                "tools": common_tools,
                "stream": True,
            },
        )
        second_text = second_raw.decode()
        assert '"type":"output_text","text":"done"' in second_text

        forwarded = upstream.seen[1]
        assistant = next(m for m in forwarded["messages"] if m.get("tool_calls"))
        tool = next(m for m in forwarded["messages"] if m.get("role") == "tool")
        assert assistant["tool_calls"][0]["id"] == "call-1"
        assert tool["tool_call_id"] == "call-1"
        assert tool["content"] == "hello"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http11_expect_100_continue_does_not_deadlock():
    server, thread, upstream = _server()
    sock = socket.create_connection(("127.0.0.1", server.server_port), timeout=2)
    sock.settimeout(2)
    try:
        body = json.dumps(
            {
                "model": "yisang-qwen",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "hello"}],
                    }
                ],
                "stream": False,
            }
        ).encode("utf-8")
        headers = (
            "POST /v1/responses HTTP/1.1\r\n"
            "Host: 127.0.0.1\r\n"
            "Content-Type: application/json; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Expect: 100-continue\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii")

        # Reproduce HttpWebRequest's handshake: send headers first and do not
        # send the JSON body until the server grants 100 Continue.
        sock.sendall(headers)
        interim = sock.recv(4096)
        assert interim.startswith(b"HTTP/1.1 100 Continue\r\n")

        sock.sendall(body)
        chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        final = b"".join(chunks)

        assert final.startswith(b"HTTP/1.1 200 OK\r\n")
        assert b'"status": "completed"' in final
        assert b'"text": "ok"' in final
        assert len(upstream.seen) == 1
    finally:
        sock.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
