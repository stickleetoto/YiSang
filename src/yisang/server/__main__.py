from __future__ import annotations

import argparse
import os
from pathlib import Path

from yisang.context.compiler import ContextCompiler
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.sqlite import SQLiteMemoryPort

from .http import create_http_server
from .proxy import YiSangModelProxy
from .upstream import OpenAIChatUpstream

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yisang-model-server",
        description="Expose YiSang as an OpenAI-compatible local model proxy.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18731)
    parser.add_argument("--model", default="yisang-qwen")
    parser.add_argument("--upstream-base-url", default="http://127.0.0.1:1234/v1")
    parser.add_argument("--upstream-model", required=True)
    parser.add_argument(
        "--upstream-api-key",
        default=os.environ.get("YISANG_UPSTREAM_API_KEY"),
    )
    parser.add_argument("--memory", default="data/yisang-model.db")
    parser.add_argument("--ego-root", default="ego")
    parser.add_argument("--project", default=str(Path.cwd()))
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Allow binding to a non-loopback host. No server auth/TLS is provided.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.host not in _LOOPBACK_HOSTS and not args.allow_remote:
        parser.error(
            "refusing non-loopback bind without --allow-remote; "
            "the built-in model server has no authentication or TLS"
        )

    memory_path = Path(args.memory)
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory = SQLiteMemoryPort(memory_path)

    ego_root = Path(args.ego_root)
    registry = EgoRegistry.from_directory(ego_root) if ego_root.exists() else EgoRegistry()

    proxy = YiSangModelProxy(
        model_id=args.model,
        upstream_model=args.upstream_model,
        identity=IdentityCharter(agent_id="yisang-model", name="YiSang"),
        state=AgentState(
            active_engine=args.upstream_model,
            active_project=args.project,
        ),
        memory=memory,
        ego_registry=registry,
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
    )
    upstream = OpenAIChatUpstream(
        base_url=args.upstream_base_url,
        api_key=args.upstream_api_key,
    )
    server = create_http_server(
        host=args.host,
        port=args.port,
        proxy=proxy,
        upstream=upstream,
    )

    print(
        f"YiSang model server: http://{args.host}:{server.server_port}/v1 "
        f"model={args.model} upstream={args.upstream_model}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        memory.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
