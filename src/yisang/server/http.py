from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from typing import Any
from urllib.parse import urlsplit

from yisang.integrations.codex import (
    DEFAULT_CODEX_CONTEXT_WINDOW,
    build_codex_model_catalog,
)

from .native_responses import (
    normalize_native_responses_response,
    prepare_native_responses_request,
)
from .proxy import YiSangModelProxy
from .responses import (
    chat_response_to_responses,
    prepare_responses_request,
    responses_sse_events,
)
from .responses_upstream import OpenAIResponsesUpstream
from .upstream import OpenAIChatUpstream, UpstreamHTTPError

_DEFAULT_MAX_BODY_BYTES = 8 * 1024 * 1024
_CLIENT_DISCONNECT_ERRORS = (
    BrokenPipeError,
    ConnectionAbortedError,
    ConnectionResetError,
)


def create_http_server(
    *,
    host: str,
    port: int,
    proxy: YiSangModelProxy,
    upstream: OpenAIChatUpstream,
    responses_upstream: OpenAIResponsesUpstream | None = None,
    max_body_bytes: int = _DEFAULT_MAX_BODY_BYTES,
    tool_profile: str = "full",
    codex_context_window: int = DEFAULT_CODEX_CONTEXT_WINDOW,
    reasoning_effort: str | None = None,
    reasoning_mode: str | None = None,
) -> ThreadingHTTPServer:
    if max_body_bytes <= 0:
        raise ValueError("max_body_bytes must be positive")
    if tool_profile not in {"full", "codex-small"}:
        raise ValueError(f"unknown tool profile: {tool_profile}")
    if codex_context_window <= 0:
        raise ValueError("codex_context_window must be positive")

    class Handler(BaseHTTPRequestHandler):
        server_version = "YiSangModelServer/0.4"
        # Windows PowerShell 5.1 uses HttpWebRequest, whose ServicePoint
        # enables Expect: 100-continue by default for POST requests. Python
        # BaseHTTPRequestHandler defaults to HTTP/1.0, which does not perform
        # the HTTP/1.1 100-continue handshake and can deadlock with such clients
        # while both sides wait for the other to proceed.
        protocol_version = "HTTP/1.1"

        def handle_expect_100(self) -> bool:
            self.send_response_only(100)
            self.end_headers()
            return True

        def do_GET(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path.rstrip("/") or "/"
            if path == "/health":
                active_upstream = (
                    responses_upstream
                    if responses_upstream is not None
                    else upstream
                )
                governor = getattr(active_upstream, "rate_limit_governor", None)
                self._send_json(
                    200,
                    {
                        "status": "ok",
                        "model": proxy.model_id,
                        "upstream_wire_api": (
                            "responses"
                            if responses_upstream is not None
                            else "chat-completions"
                        ),
                        "reasoning_effort": reasoning_effort,
                        "reasoning_mode": reasoning_mode,
                        "tool_profile": tool_profile,
                        "rate_limit": (
                            governor.snapshot().to_dict()
                            if governor is not None
                            else None
                        ),
                    },
                )
                return
            if path == "/v1/models":
                self._send_json(
                    200,
                    {
                        "object": "list",
                        "data": [
                            {
                                "id": proxy.model_id,
                                "object": "model",
                                "owned_by": "yisang",
                            }
                        ],
                    },
                )
                return
            if path == "/v1/codex/models":
                self._send_json(
                    200,
                    build_codex_model_catalog(
                        proxy.model_id,
                        context_window=codex_context_window,
                    ),
                )
                return
            self._send_error(404, "not_found", "route not found")

        def do_POST(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path.rstrip("/") or "/"
            if path not in {"/v1/chat/completions", "/v1/responses"}:
                self._send_error(404, "not_found", "route not found")
                return

            try:
                body = self._read_json_body()
                if path == "/v1/responses":
                    self._handle_responses(body)
                    return
                self._handle_chat(body)
            except ValueError as exc:
                self._send_error(400, "invalid_request_error", str(exc))
            except UpstreamHTTPError as exc:
                self._send_upstream_error(exc)
            except Exception as exc:  # containment boundary for the local server
                self._send_error(500, "internal_error", f"{type(exc).__name__}: {exc}")

        def _handle_chat(self, body: dict[str, Any]) -> None:
            prepared = proxy.prepare_chat_request(body)
            if prepared.payload.get("stream"):
                self._stream_chat(prepared.payload)
                return

            response = upstream.complete(prepared.payload)
            self._send_json(200, proxy.normalize_chat_response(response))

        def _handle_responses(self, body: dict[str, Any]) -> None:
            if responses_upstream is not None:
                prepared_native = prepare_native_responses_request(
                    proxy,
                    body,
                    tool_profile=tool_profile,
                    reasoning_effort=reasoning_effort,
                    reasoning_mode=reasoning_mode,
                )
                native_response = responses_upstream.complete(prepared_native.payload)
                response = normalize_native_responses_response(
                    proxy,
                    native_response,
                )
                if prepared_native.stream:
                    self._send_responses_sse(response)
                else:
                    self._send_json(200, response)
                return

            prepared = prepare_responses_request(
                proxy,
                body,
                tool_profile=tool_profile,
            )
            # Legacy bridge: complete an upstream Chat response, then render
            # Responses events. This keeps Ollama/local backends compatible.
            chat_response = upstream.complete(prepared.chat_payload)
            response = chat_response_to_responses(
                proxy=proxy,
                chat_response=chat_response,
                tool_metadata=prepared.tool_metadata,
                recover_text_tool_calls=(tool_profile == "codex-small"),
            )
            if prepared.stream:
                self._send_responses_sse(response)
            else:
                self._send_json(200, response)

        def _read_json_body(self) -> dict[str, Any]:
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                raise ValueError("Content-Length is required")
            try:
                length = int(raw_length)
            except ValueError as exc:
                raise ValueError("invalid Content-Length") from exc
            if length < 0 or length > max_body_bytes:
                raise ValueError("request body exceeds server limit")

            raw = self.rfile.read(length)
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("request body must be valid UTF-8 JSON") from exc
            if not isinstance(body, dict):
                raise ValueError("request body must be a JSON object")
            return body

        def _stream_chat(self, payload: dict[str, Any]) -> None:
            # Prefetch one event before sending 200 so an upstream HTTP failure is
            # still representable as a clean 502 JSON response.
            events = iter(upstream.stream(payload))
            try:
                first = next(events)
            except StopIteration:
                first = None

            if not self._start_sse():
                return

            if first is not None and not self._write_response_bytes(
                proxy.normalize_sse_line(first),
                flush=True,
            ):
                return
            for line in events:
                if not self._write_response_bytes(
                    proxy.normalize_sse_line(line),
                    flush=True,
                ):
                    return

        def _send_responses_sse(self, response: dict[str, Any]) -> None:
            if not self._start_sse():
                return
            for event in responses_sse_events(response):
                if not self._write_response_bytes(event, flush=True):
                    return

        def _start_sse(self) -> bool:
            try:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                return True
            except _CLIENT_DISCONNECT_ERRORS:
                return False

        def _write_response_bytes(self, data: bytes, *, flush: bool = False) -> bool:
            try:
                self.wfile.write(data)
                if flush:
                    self.wfile.flush()
                return True
            except _CLIENT_DISCONNECT_ERRORS:
                # The client may cancel a long-running local inference or close
                # the socket after receiving enough data. This is not a server
                # failure and must not trigger a second error response.
                return False

        def _send_json(
            self,
            status: int,
            payload: dict[str, Any],
            *,
            headers: dict[str, str] | None = None,
        ) -> bool:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                for name, value in (headers or {}).items():
                    self.send_header(name, value)
                self.end_headers()
            except _CLIENT_DISCONNECT_ERRORS:
                return False
            return self._write_response_bytes(encoded)

        def _send_upstream_error(self, exc: UpstreamHTTPError) -> None:
            retry_after = (
                max(1, math.ceil(exc.retry_after))
                if exc.retry_after is not None
                else None
            )
            self.log_message(
                "upstream failure status=%s locally_blocked=%s retry_after=%s",
                exc.status,
                exc.locally_blocked,
                retry_after,
            )

            headers = (
                {"Retry-After": str(retry_after)}
                if retry_after is not None
                else None
            )

            if exc.status == 429:
                self._send_json(
                    429,
                    {
                        "error": {
                            "message": str(exc),
                            "type": "upstream_rate_limited",
                            "code": "upstream_rate_limited",
                            "upstream_status": 429,
                            "retry_after": retry_after or 1,
                            "locally_blocked": exc.locally_blocked,
                        }
                    },
                    headers=headers or {"Retry-After": "1"},
                )
                return

            if 400 <= exc.status <= 499:
                self._send_json(
                    exc.status,
                    {
                        "error": {
                            "message": str(exc),
                            "type": "upstream_client_error",
                            "code": f"upstream_http_{exc.status}",
                            "upstream_status": exc.status,
                            "locally_blocked": exc.locally_blocked,
                        }
                    },
                    headers=headers,
                )
                return

            if 500 <= exc.status <= 599:
                self._send_json(
                    exc.status,
                    {
                        "error": {
                            "message": str(exc),
                            "type": "upstream_service_error",
                            "code": f"upstream_http_{exc.status}",
                            "upstream_status": exc.status,
                            "retry_after": retry_after,
                            "locally_blocked": exc.locally_blocked,
                        }
                    },
                    headers=headers,
                )
                return

            self._send_error(502, "upstream_error", str(exc))

        def _send_error(self, status: int, code: str, message: str) -> None:
            self._send_json(
                status,
                {
                    "error": {
                        "message": message,
                        "type": code,
                        "code": code,
                    }
                },
            )

    return ThreadingHTTPServer((host, port), Handler)