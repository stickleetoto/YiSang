from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from typing import Any
from urllib.parse import urlsplit

from .proxy import YiSangModelProxy
from .upstream import OpenAIChatUpstream, UpstreamHTTPError

_DEFAULT_MAX_BODY_BYTES = 8 * 1024 * 1024


def create_http_server(
    *,
    host: str,
    port: int,
    proxy: YiSangModelProxy,
    upstream: OpenAIChatUpstream,
    max_body_bytes: int = _DEFAULT_MAX_BODY_BYTES,
) -> ThreadingHTTPServer:
    if max_body_bytes <= 0:
        raise ValueError("max_body_bytes must be positive")

    class Handler(BaseHTTPRequestHandler):
        server_version = "YiSangModelServer/0.3"

        def do_GET(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path.rstrip("/") or "/"
            if path == "/health":
                self._send_json(200, {"status": "ok", "model": proxy.model_id})
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
            self._send_error(404, "not_found", "route not found")

        def do_POST(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path.rstrip("/") or "/"
            if path == "/v1/responses":
                self._send_error(
                    501,
                    "responses_not_implemented",
                    "YiSang v0.3 model server currently supports the Chat "
                    "Completions wire protocol. Configure Codex with wire_api=\"chat\".",
                )
                return
            if path != "/v1/chat/completions":
                self._send_error(404, "not_found", "route not found")
                return

            try:
                body = self._read_json_body()
                prepared = proxy.prepare_chat_request(body)
                if prepared.payload.get("stream"):
                    self._stream_chat(prepared.payload)
                    return

                response = upstream.complete(prepared.payload)
                self._send_json(200, proxy.normalize_chat_response(response))
            except ValueError as exc:
                self._send_error(400, "invalid_request_error", str(exc))
            except UpstreamHTTPError as exc:
                self._send_error(502, "upstream_error", str(exc))
            except Exception as exc:  # containment boundary for the local server
                self._send_error(500, "internal_error", f"{type(exc).__name__}: {exc}")

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

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()

            if first is not None:
                self.wfile.write(proxy.normalize_sse_line(first))
                self.wfile.flush()
            for line in events:
                self.wfile.write(proxy.normalize_sse_line(line))
                self.wfile.flush()

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

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
