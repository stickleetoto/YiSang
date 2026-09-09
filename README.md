# YiSang

**YiSang is a model-independent LLM enhancement layer.**

> Models are replaceable. Memory and capability remain.

YiSang keeps durable agent assets outside the attached model:

- identity and runtime state
- external memory
- E.G.O capability packs
- context compilation
- guarded tool execution
- verification and governance

## v0.3 direction: YiSang as the model

YiSang can now sit **behind an agent harness such as Codex** and present itself
as an OpenAI-compatible model endpoint:

```text
Codex
  |
  | model = yisang-qwen
  v
YiSang Model Server
  |
  +-- Memory
  +-- E.G.O
  +-- Context Compiler
  +-- Identity / State
  |
  v
Qwen / local OpenAI-compatible model
```

In this mode, Codex keeps its own tools, shell, sandbox, approvals, and agent
loop. YiSang preserves Codex tool schemas on the request and passes Qwen tool
calls back to Codex for execution.

Current model-server surface:

```text
GET  /health
GET  /v1/models
POST /v1/chat/completions
```

Both normal Chat Completions and SSE streaming are supported. Responses API
compatibility is the next protocol milestone.

## Existing v0.2 foundation

The v0.3 model-server branch is based on the v0.2 development line, which
already provides:

- persistent `SQLiteMemoryPort`
- OpenAI-compatible local LLM engine
- model-agnostic context budgets
- deterministic context rendering
- E.G.O loading from `manifest.json` + `SKILL.md`
- engine-swap invariance probe
- typed `ToolRegistry`
- E.G.O capability + permission `ActionGate`
- side-effect tools disabled by default
- structured action decoding
- bounded tool-feedback loop
- read-only workspace tools with path confinement
- GitHub Actions tests on Python 3.11 / 3.12

BIO remains a future `MemoryPort` adapter rather than a YiSang dependency.

## Install

```bash
python -m pip install -e .[dev]
pytest -q
```

## Start YiSang as a local model

Assuming LM Studio is serving Qwen at `http://127.0.0.1:1234/v1`:

```powershell
yisang-model-server `
  --upstream-base-url http://127.0.0.1:1234/v1 `
  --upstream-model YOUR_LM_STUDIO_MODEL_ID `
  --model yisang-qwen
```

YiSang then exposes:

```text
http://127.0.0.1:18731/v1
```

For Codex, configure a custom provider with:

```toml
model = "yisang-qwen"
model_provider = "yisang"

[model_providers.yisang]
name = "YiSang Local"
base_url = "http://127.0.0.1:18731/v1"
wire_api = "chat"
requires_openai_auth = false
```

See `docs/CODEX_MODEL_SERVER.md` for the full flow.

## Core invariants

1. `YiSang != the attached base model`.
2. Engine replacement must not reset memory.
3. Engine replacement must not reset capabilities.
4. Model output is not authoritative memory.
5. Memory writes pass through proposal + governance.
6. E.G.O is external capability data, not model weights.
7. Model-proposed actions do not create execution authority.
8. Side-effecting YiSang tools are opt-in.
9. Tool output is evidence, not instruction authority.
10. Tool loops are bounded.
11. In Codex model-server mode, Codex retains client-tool execution authority.
12. Core depends on interfaces, not model providers.

See `docs/ARCHITECTURE.md`, `docs/EXECUTION.md`, `docs/CODEX_MODEL_SERVER.md`,
and `docs/HANDOFF.md`.
