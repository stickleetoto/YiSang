from __future__ import annotations

import os
from pathlib import Path

from yisang.context.compiler import ContextCompiler
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.openai_compatible import OpenAICompatibleEngine
from yisang.engines.router import EngineRouter
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.sqlite import SQLiteMemoryPort

from .gateway import YiSangModelGateway
from .http import serve


def main() -> None:
    model_id = os.getenv("YISANG_MODEL_ID", "yisang-qwen")
    upstream_model = os.getenv("YISANG_UPSTREAM_MODEL", "qwen")
    upstream_base = os.getenv("YISANG_UPSTREAM_BASE_URL", "http://127.0.0.1:1234/v1")
    host = os.getenv("YISANG_HOST", "127.0.0.1")
    port = int(os.getenv("YISANG_PORT", "18731"))
    memory_path = Path(os.getenv("YISANG_MEMORY_DB", "data/yisang-model-server.db"))
    ego_path = Path(os.getenv("YISANG_EGO_DIR", "ego"))

    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory = SQLiteMemoryPort(memory_path)
    egos = EgoRegistry.from_directory(ego_path) if ego_path.exists() else EgoRegistry()

    engines = EngineRouter()
    engines.register(OpenAICompatibleEngine(
        engine_id="upstream-qwen",
        base_url=upstream_base,
        model=upstream_model,
        structured_actions=True,
    ))

    gateway = YiSangModelGateway(
        model_id=model_id,
        identity=IdentityCharter("yisang-model-server", "YiSang"),
        state=AgentState(active_engine="upstream-qwen", active_project="model-server"),
        memory=memory,
        ego_registry=egos,
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
    )

    print(f"YiSang model server: http://{host}:{port}/v1")
    print(f"model: {model_id} -> {upstream_model} @ {upstream_base}")
    serve(gateway, host=host, port=port)


if __name__ == "__main__":
    main()
