from __future__ import annotations

import json
import socket
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


class MalformedTypedToolUpstream(FakeUpstream):
    def complete(self, payload):
        self.seen.append(payload)
        return {
            "id": "chatcmpl-typed",
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
                                "id": "call-typed",
                                "type": "function",
                                "function": {
                                    "name": "typed_tool",
                                    "arguments": json.dumps(
                                        {
                                            "paths": "['result.txt']",
                                            "limit": "100",
                                            "ratio": "1.5",
                                            "enabled": "false",
                                            "options": "{'mode': 'fast'}",
                                        }
                                    ),
                                },
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ],
        }


class TextualToolCallUpstream(FakeUpstream):
    def complete(self, payload):
        self.seen.append(payload)
        return {
            "id": "chatcmpl-text-tool",
            "object": "chat.completion",
            "model": payload["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": (
                            '{"name":"exec_command","parameters":'
                            '{"cmd":"Get-Content test.txt"}}'
                        ),
                    },
                    "finish_reason": "stop",
                }
            ],
        }


class NamespacedTextualToolCallUpstream(FakeUpstream):
    def complete(self, payload):
        self.seen.append(payload)
        arguments = {
            "cmd": "Get-Content test.txt",
            "justification": "",
            "login": True,
            "max_output_tokens": 1000,
            "prefix_rule": [],
            "sandbox_permissions": "use_default",
            "shell": "cmd /c",
            "tty": False,
            "workdir": r"C:\\tmp\\yisang-codex-e2e",
            "yield_time_ms": 10000,
        }
        return {
            "id": "chatcmpl-text-namespaced",
            "object": "chat.completion",
            "model": payload["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {
                                "name": "exec_command",
                                "parameters": json.dumps(arguments),
                            }
                        ),
                    },
                    "finish_reason": "stop",
                }
            ],
        }


class TextualUnknownToolUpstream(FakeUpstream):
    def complete(self, payload):
        self.seen.append(payload)
        return {
            "id": "chatcmpl-text-unknown",
            "object": "chat.completion",
            "model": payload["model"],
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": '{"name":"read_stdin","parameters":{"chars":"x"}}',
                    },
                    "finish_reason": "stop",
                }
            ],
        }


class FailingStreamUpstream(FakeUpstream):
    def stream(self, payload):
        raise UpstreamHTTPError(503, "model unavailable")
        yield b""  # pragma: no cover


def _server(upstream=None, *, tool_profile="full"):
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
        tool_profile=tool_profile,
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


def test_responses_repairs_tool_argument_types_from_schema():
    server, thread, _ = _server(MalformedTypedToolUpstream())
    try:
        _, _, raw = _post_json(
            server,
            "/v1/responses",
            {
                "model": "yisang-qwen",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "use the typed tool"}],
                    }
                ],
                "tools": [
                    {
                        "type": "function",
                        "name": "typed_tool",
                        "description": "Exercise typed arguments",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "paths": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "limit": {"type": "integer"},
                                "ratio": {"type": "number"},
                                "enabled": {"type": "boolean"},
                                "options": {
                                    "type": "object",
                                    "properties": {
                                        "mode": {"type": "string"},
                                    },
                                },
                            },
                        },
                    }
                ],
                "stream": False,
            },
        )
        response = json.loads(raw)
        item = response["output"][0]
        arguments = json.loads(item["arguments"])

        assert item["type"] == "function_call"
        assert arguments["paths"] == ["result.txt"]
        assert arguments["limit"] == 100
        assert arguments["ratio"] == 1.5
        assert arguments["enabled"] is False
        assert arguments["options"] == {"mode": "fast"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_codex_small_profile_filters_tools_and_recovers_textual_tool_call():
    server, thread, upstream = _server(
        TextualToolCallUpstream(),
        tool_profile="codex-small",
    )
    try:
        _, _, raw = _post_json(
            server,
            "/v1/responses",
            {
                "model": "yisang-qwen",
                "instructions": "Use local coding tools.",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "read test.txt"}],
                    }
                ],
                "tools": [
                    {
                        "type": "function",
                        "name": "exec_command",
                        "description": "Run a command",
                        "parameters": {
                            "type": "object",
                            "properties": {"cmd": {"type": "string"}},
                            "required": ["cmd"],
                        },
                    },
                    {
                        "type": "function",
                        "name": "read_stdin",
                        "description": "Read a terminal",
                        "parameters": {"type": "object"},
                    },
                    {
                        "type": "function",
                        "name": "write_stdin",
                        "description": "Write to a terminal",
                        "parameters": {"type": "object"},
                    },
                    {
                        "type": "custom",
                        "name": "apply_patch",
                        "description": "Apply a patch",
                    },
                ],
                "stream": False,
            },
        )
        response = json.loads(raw)
        forwarded = upstream.seen[0]
        forwarded_names = [
            tool["function"]["name"]
            for tool in forwarded["tools"]
        ]

        assert forwarded_names == ["exec_command", "apply_patch"]
        assert forwarded["parallel_tool_calls"] is False
        assert any(
            "YISANG CODEX SMALL-MODEL TOOL PROFILE" in str(message.get("content"))
            for message in forwarded["messages"]
        )

        item = response["output"][0]
        assert item["type"] == "function_call"
        assert item["name"] == "exec_command"
        assert json.loads(item["arguments"]) == {"cmd": "Get-Content test.txt"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_codex_small_profile_recovers_unqualified_namespaced_tool_with_string_parameters():
    server, thread, upstream = _server(
        NamespacedTextualToolCallUpstream(),
        tool_profile="codex-small",
    )
    try:
        _, _, raw = _post_json(
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
                "tools": [
                    {
                        "type": "namespace",
                        "name": "functions",
                        "tools": [
                            {
                                "type": "function",
                                "name": "exec_command",
                                "description": "Run a command",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "cmd": {"type": "string"},
                                        "justification": {"type": "string"},
                                        "login": {"type": "boolean"},
                                        "max_output_tokens": {"type": "integer"},
                                        "prefix_rule": {"type": "array"},
                                        "sandbox_permissions": {"type": "string"},
                                        "shell": {"type": "string"},
                                        "tty": {"type": "boolean"},
                                        "workdir": {"type": "string"},
                                        "yield_time_ms": {"type": "integer"},
                                    },
                                    "required": ["cmd"],
                                },
                            }
                        ],
                    }
                ],
                "stream": False,
            },
        )
        response = json.loads(raw)
        forwarded = upstream.seen[0]
        assert forwarded["tools"][0]["function"]["name"] == "functions__exec_command"

        item = response["output"][0]
        assert item["type"] == "function_call"
        assert item["name"] == "exec_command"
        assert item["namespace"] == "functions"
        arguments = json.loads(item["arguments"])
        assert arguments["cmd"] == "Get-Content test.txt"
        assert arguments["login"] is True
        assert arguments["max_output_tokens"] == 1000
        assert arguments["prefix_rule"] == []
        assert arguments["yield_time_ms"] == 10000
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_codex_small_profile_does_not_promote_unknown_textual_tool():
    server, thread, _ = _server(
        TextualUnknownToolUpstream(),
        tool_profile="codex-small",
    )
    try:
        _, _, raw = _post_json(
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
                "tools": [
                    {
                        "type": "function",
                        "name": "exec_command",
                        "description": "Run a command",
                        "parameters": {"type": "object"},
                    },
                    {
                        "type": "function",
                        "name": "read_stdin",
                        "description": "Read a terminal",
                        "parameters": {"type": "object"},
                    },
                ],
                "stream": False,
            },
        )
        response = json.loads(raw)
        item = response["output"][0]
        assert item["type"] == "message"
        assert "read_stdin" in item["content"][0]["text"]
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
