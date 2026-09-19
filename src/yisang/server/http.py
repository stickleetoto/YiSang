from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from .gateway import YiSangModelGateway
from .protocol import ProtocolError, error_payload

MAX_BODY_BYTES = 4 * 1024 * 1024


def create_server(
    gateway: YiSangModelGateway,
    *,
    host: str = "127.0.0.1",
    port: int = 18731,
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = "YiSangModelServer/0.1"

        def do_GET(self) -> None:  # noqa: N802
            path = urlsplit(self.path).path
            if path == "/health":
                self._json(200, {"status": "ok", "model": gateway.model_id})
                return
            if path == "/v1/models":
                self._json(200, gateway.models())
                return
            self._json(404, error_payload(ProtocolError("not found", code="not_found", status=404)))

        def do_POST(self) -> None:  # noqa: N802
            try:
                payload = self._read_json()
                path = urlsplit(self.path).path
                if path == "/v1/chat/completions":
                    response = gateway.chat_completions(payload)
                elif path == "/v1/responses":
                    response = gateway.responses(payload)
                else:
                    raise ProtocolError("not found", code="not_found", status=404)
                self._json(200, response)
            except ProtocolError as exc:
                self._json(exc.status, error_payload(exc))
            except Exception as exc:
                self._json(500, {
                    "error": {
                        "message": f"internal server error: {type(exc).__name__}",
                        "type": "server_error",
                        "param": None,
                        "code": "internal_error",
                    }
                })

        def _read_json(self) -> dict[str, Any]:
            raw_length = self.headers.get("Content-Length")
            try:
                length = int(raw_length or "0")
            except ValueError as exc:
                raise ProtocolError("invalid Content-Length") from exc
            if length <= 0:
                raise ProtocolError("request body is required")
            if length > MAX_BODY_BYTES:
                raise ProtocolError("request body too large", code="request_too_large", status=413)
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ProtocolError("request body must be valid UTF-8 JSON") from exc
            if not isinstance(payload, dict):
                raise ProtocolError("request body must be a JSON object")
            return payload

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def serve(gateway: YiSangModelGateway, *, host: str = "127.0.0.1", port: int = 18731) -> None:
    server = create_server(gateway, host=host, port=port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
