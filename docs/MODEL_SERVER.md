# YiSang Model Server

## Goal

Expose YiSang as a model-compatible cognitive proxy:

```text
Codex / client
      |
      | OpenAI-compatible model request
      v
YiSang Model Server
      |
      +-- identity
      +-- persistent memory retrieval
      +-- E.G.O routing
      +-- context compilation
      |
      v
replaceable upstream engine (Qwen first)
```

The client sees one stable model id such as `yisang-qwen`. The upstream model can
change without changing the client-facing model identity.

## Delegated tool mode

Model-server mode deliberately differs from standalone YiSang execution:

```text
Standalone mode: model -> YiSang ActionGate -> YiSang tool runtime
Model-server mode: model -> function/tool call -> client (Codex) executes it
```

Client-provided function tool schemas are compiled into the upstream model
context. YiSang does not execute those delegated tools and returns requested
calls using the client protocol.

## Endpoints (foundation)

- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/responses`

The foundation is non-streaming. Requests with `stream: true` fail closed until
SSE streaming is implemented.

## Run against LM Studio / Qwen

```powershell
$env:YISANG_UPSTREAM_BASE_URL="http://127.0.0.1:1234/v1"
$env:YISANG_UPSTREAM_MODEL="your-qwen-model-id"
$env:YISANG_MODEL_ID="yisang-qwen"
python -m yisang.server
```

Default YiSang endpoint:

```text
http://127.0.0.1:18731/v1
```

## Compatibility scope

This milestone is a protocol foundation, not a claim of complete Codex
compatibility. Codex-oriented work should prioritize the Responses API, function
calling and streaming. Current OpenAI API guidance recommends Responses for
reasoning/tool-calling use cases, so `/v1/responses` is treated as a first-class
surface rather than an optional later shim.

## Security boundary

Delegated tool definitions describe capabilities owned by the client. They do
not grant YiSang local execution authority. YiSang's standalone ActionGate and
client-delegated tool mode remain separate authority domains.
