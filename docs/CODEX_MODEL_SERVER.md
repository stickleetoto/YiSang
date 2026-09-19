# YiSang as a Codex Model Backend

## Goal

Run Codex with YiSang as the configured model provider:

```text
Codex agent harness
      |
      | OpenAI-compatible Chat Completions
      v
YiSang model server
      |
      +-- Identity / state
      +-- Memory retrieval
      +-- E.G.O routing
      +-- Context compilation
      |
      v
Qwen / other OpenAI-compatible local model
```

Codex remains responsible for its own repository tools, shell, sandbox, approvals,
and agent loop. YiSang is the model-compatible cognitive layer in front of Qwen.

## Tool ownership

This integration intentionally does **not** execute Codex tools inside YiSang.

```text
Codex tool schema
      |
      v
YiSang preserves it
      |
      v
Qwen emits tool_calls
      |
      v
YiSang preserves them
      |
      v
Codex executes the tool
```

This keeps Codex's existing agent harness intact while changing only the model
backend.

## 1. Start the upstream local model

Example target: LM Studio on its usual OpenAI-compatible endpoint:

```text
http://127.0.0.1:1234/v1
```

Load the desired Qwen model and note the exact served model id.

## 2. Start YiSang model server

Install the branch:

```powershell
python -m pip install -e .[dev]
```

Then run:

```powershell
yisang-model-server `
  --upstream-base-url http://127.0.0.1:1234/v1 `
  --upstream-model YOUR_LM_STUDIO_MODEL_ID `
  --model yisang-qwen
```

Default YiSang endpoint:

```text
http://127.0.0.1:18731/v1
```

Smoke checks:

```powershell
Invoke-RestMethod http://127.0.0.1:18731/health
Invoke-RestMethod http://127.0.0.1:18731/v1/models
```

The model list should expose:

```text
yisang-qwen
```

## 3. Configure Codex

For the first smoke test, use the user-level Codex config on Windows:

```text
%USERPROFILE%\.codex\config.toml
```

Example:

```toml
model = "yisang-qwen"
model_provider = "yisang"

[model_providers.yisang]
name = "YiSang Local"
base_url = "http://127.0.0.1:18731/v1"
wire_api = "chat"
requires_openai_auth = false
```

Then start Codex normally.

YiSang v0.3 deliberately targets Codex's Chat Completions wire mode first.
`POST /v1/responses` currently returns an actionable `501` response instead of
silently pretending to support the Responses protocol.

## What YiSang adds to every model request

Before forwarding the Codex request upstream, YiSang injects a system context
containing the current:

- YiSang identity
- agent/project state
- relevant external memories
- routed E.G.O capability instructions
- YiSang safety/continuity constraints

The original Codex messages and tool schemas remain present after the YiSang
augmentation message.

## Streaming

If Codex sends `stream=true`, YiSang proxies OpenAI-style SSE chunks from the
upstream model and rewrites only the exposed model id back to `yisang-qwen`.
Tool-call deltas and other chunk data are otherwise preserved.

## Current protocol surface

Implemented:

```text
GET  /health
GET  /v1/models
POST /v1/chat/completions
```

Supported Chat Completions behavior:

- normal JSON completions
- SSE streaming
- client message passthrough
- client tool schema passthrough
- upstream tool-call passthrough
- model alias normalization

Not implemented yet:

- `/v1/responses`
- Responses streaming event translation
- exact tokenizer-aware usage accounting for YiSang-injected context
- server-side authentication
- multi-model routing behind one YiSang endpoint

## Security boundary

The server binds to `127.0.0.1` by default. Keep it loopback-only unless a
separate authentication/TLS boundary is intentionally added.

The key invariant for Codex mode is:

> YiSang augments model cognition; Codex retains execution authority.
