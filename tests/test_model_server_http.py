import json
import threading
from urllib import error as urllib_error
from urllib import request as urllib_request

from yisang.context.compiler import ContextCompiler
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.base import EngineResult, LLMEngine
from yisang.engines.router import EngineRouter
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.server.gateway import YiSangModelGateway
from yisang.server.http import create_server


class TextEngine(LLMEngine):
    engine_id = "text"

    def generate(self, context):
        return EngineResult(engine_id=self.engine_id, text="server-ok")


def _gateway():
    engines = EngineRouter()
    engines.register(TextEngine())
    return YiSangModelGateway(
        model_id="yisang-qwen",
        identity=IdentityCharter("server-test", "YiSang"),
        state=AgentState(active_engine="text"),
        memory=InMemoryMemoryPort(),
        ego_registry=EgoRegistry(),
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
    )


def _json_request(url, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    with urllib_request.urlopen(req, timeout=3) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_http_model_server_routes_models_chat_and_responses():
    server = create_server(_gateway(), host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    base = f"http://{host}:{port}"
    try:
        status, models = _json_request(base + "/v1/models")
        assert status == 200
        assert models["data"][0]["id"] == "yisang-qwen"

        _, chat = _json_request(base + "/v1/chat/completions", {
            "model": "yisang-qwen",
            "messages": [{"role": "user", "content": "hi"}],
        })
        assert chat["choices"][0]["message"]["content"] == "server-ok"

        _, response = _json_request(base + "/v1/responses", {
            "model": "yisang-qwen",
            "input": "hi",
        })
        assert response["output_text"] == "server-ok"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_http_errors_use_openai_style_error_envelope():
    server = create_server(_gateway(), host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        try:
            _json_request(f"http://{host}:{port}/v1/responses", {
                "model": "wrong",
                "input": "hi",
            })
        except urllib_error.HTTPError as exc:
            body = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 404
            assert body["error"]["code"] == "model_not_found"
        else:
            raise AssertionError("invalid model did not return an HTTP error")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
