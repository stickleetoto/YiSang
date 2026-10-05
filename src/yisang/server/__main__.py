from __future__ import annotations

import argparse
import os
from pathlib import Path

from yisang.context.compiler import ContextCompiler
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.identity.models import AgentState, IdentityCharter
from yisang.integrations.codex import DEFAULT_CODEX_CONTEXT_WINDOW
from yisang.memory.sqlite import SQLiteMemoryPort

from .http import create_http_server
from .proxy import YiSangModelProxy
from .rate_limit import RateLimitGovernor
from .responses_upstream import OpenAIResponsesUpstream
from .upstream import OpenAIChatUpstream

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
_REASONING_MODES = ("standard", "pro")


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
        "--upstream-wire-api",
        choices=("chat-completions", "responses"),
        default="chat-completions",
        help=(
            "Protocol YiSang uses to call the attached model. Use 'responses' "
            "for GPT-6 reasoning with tools; keep 'chat-completions' for local "
            "OpenAI-compatible backends such as Ollama."
        ),
    )
    parser.add_argument(
        "--upstream-api-key",
        default=os.environ.get("YISANG_UPSTREAM_API_KEY"),
    )
    parser.add_argument(
        "--upstream-timeout",
        type=float,
        default=1800.0,
        help="Upstream request timeout in seconds.",
    )
    parser.add_argument(
        "--upstream-min-interval",
        type=float,
        default=2.0,
        help=(
            "Minimum seconds between upstream request starts. This serializes "
            "fast Codex tool loops before they can burst against a provider."
        ),
    )
    parser.add_argument(
        "--upstream-rate-limit-backoff",
        type=float,
        default=2.0,
        help="Initial local cooldown after an upstream HTTP 429.",
    )
    parser.add_argument(
        "--upstream-rate-limit-max-backoff",
        type=float,
        default=60.0,
        help="Maximum exponential local cooldown after repeated upstream 429s.",
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=_REASONING_EFFORTS,
        default=None,
        help=(
            "Force Responses reasoning.effort. Recommended for Luna agentic "
            "development: xhigh; reserve max for measured quality-first cases."
        ),
    )
    parser.add_argument(
        "--reasoning-mode",
        choices=_REASONING_MODES,
        default=None,
        help="Force Responses reasoning.mode (standard or pro).",
    )
    parser.add_argument("--memory", default="data/yisang-model.db")
    parser.add_argument("--ego-root", default="ego")
    parser.add_argument("--project", default=str(Path.cwd()))
    parser.add_argument(
        "--codex-context-window",
        type=int,
        default=DEFAULT_CODEX_CONTEXT_WINDOW,
        help="Context window advertised by /v1/codex/models.",
    )
    parser.add_argument(
        "--tool-profile",
        choices=("full", "codex-small"),
        default="full",
        help=(
            "Tool exposure profile for Responses clients. "
            "'codex-small' keeps only simple local coding tools and enables "
            "conservative recovery of textual tool-call JSON for small models. "
            "Use 'full' when Codex MCP tools such as mcp-hand must reach the model."
        ),
    )
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
    if args.upstream_timeout <= 0:
        parser.error("--upstream-timeout must be positive")
    if args.upstream_min_interval < 0:
        parser.error("--upstream-min-interval must be non-negative")
    if args.upstream_rate_limit_backoff <= 0:
        parser.error("--upstream-rate-limit-backoff must be positive")
    if args.upstream_rate_limit_max_backoff < args.upstream_rate_limit_backoff:
        parser.error(
            "--upstream-rate-limit-max-backoff must be >= "
            "--upstream-rate-limit-backoff"
        )
    if (
        args.upstream_wire_api != "responses"
        and (args.reasoning_effort is not None or args.reasoning_mode is not None)
    ):
        parser.error(
            "--reasoning-effort/--reasoning-mode require "
            "--upstream-wire-api responses"
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
    rate_limit_governor = RateLimitGovernor(
        min_interval=args.upstream_min_interval,
        backoff_initial=args.upstream_rate_limit_backoff,
        backoff_max=args.upstream_rate_limit_max_backoff,
    )
    upstream = OpenAIChatUpstream(
        base_url=args.upstream_base_url,
        api_key=args.upstream_api_key,
        timeout=args.upstream_timeout,
        rate_limit_governor=rate_limit_governor,
    )
    responses_upstream = (
        OpenAIResponsesUpstream(
            base_url=args.upstream_base_url,
            api_key=args.upstream_api_key,
            timeout=args.upstream_timeout,
            rate_limit_governor=rate_limit_governor,
        )
        if args.upstream_wire_api == "responses"
        else None
    )
    server = create_http_server(
        host=args.host,
        port=args.port,
        proxy=proxy,
        upstream=upstream,
        responses_upstream=responses_upstream,
        tool_profile=args.tool_profile,
        codex_context_window=args.codex_context_window,
        reasoning_effort=args.reasoning_effort,
        reasoning_mode=args.reasoning_mode,
    )

    print(
        f"YiSang model server: http://{args.host}:{server.server_port}/v1 "
        f"model={args.model} upstream={args.upstream_model} "
        f"wire={args.upstream_wire_api} "
        f"reasoning={args.reasoning_effort or 'upstream-default'}/"
        f"{args.reasoning_mode or 'upstream-default'} "
        f"min_interval={args.upstream_min_interval}s "
        f"rate_backoff={args.upstream_rate_limit_backoff}-"
        f"{args.upstream_rate_limit_max_backoff}s "
        f"tool_profile={args.tool_profile} "
        f"codex_context_window={args.codex_context_window}"
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