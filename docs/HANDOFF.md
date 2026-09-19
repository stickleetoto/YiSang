# YiSang Handoff

## Current target

**v0.3.0 development — OpenAI-compatible YiSang Model Server**

## Core thesis

YiSang is not the attached base LLM. YiSang is the persistent cognitive layer
that can itself be exposed as a model to an external agent harness.

```text
Codex / client agent
        |
        v
YiSang model-compatible proxy
        |
        +-- identity/state
        +-- memory
        +-- E.G.O
        +-- context compiler
        |
        v
replaceable Qwen / local model
```

## v0.3 implemented

- `YiSangModelProxy`
- stdlib-only HTTP server
- `GET /health`
- `GET /v1/models`
- `POST /v1/chat/completions`
- non-streaming completion proxy
- SSE streaming proxy
- YiSang model alias rewriting
- original client message preservation
- original client tool-schema preservation
- upstream tool-call preservation
- YiSang memory retrieval before each model request
- E.G.O routing before each model request
- YiSang context injection before the original conversation
- `yisang-model-server` CLI entry point
- explicit unsupported `/v1/responses` error
- HTTP/proxy regression tests

## Codex ownership model

In Codex mode:

```text
Codex owns:
- shell
- repository mutations
- tool execution
- sandbox
- approvals
- agent loop

YiSang owns:
- persistent cognition layer
- memory retrieval
- E.G.O selection
- context augmentation
- attached base-model selection
```

Codex tool schemas are passed through YiSang to Qwen. Qwen tool calls are passed
back through YiSang to Codex. YiSang does not steal Codex's tool executor.

## v0.2 inherited foundation

- SQLite persistent `MemoryPort`
- OpenAI-compatible engine adapter
- context budgeting
- E.G.O directory loader
- model invariance probe
- guarded standalone action runtime
- verification/governance
- bounded internal tool-feedback loop
- read-only workspace tools
- Python 3.11 / 3.12 CI

## Guardrails

- BIO is not a dependency yet.
- Do not make base-model output authoritative memory.
- Keep memory and E.G.O outside Qwen.
- Preserve external client tools exactly unless protocol translation requires a
  deterministic transformation.
- Do not execute Codex-owned tools inside YiSang model-server mode.
- Bind to loopback by default.
- Do not claim Responses API compatibility until its event and tool protocol is
  actually implemented and tested.

## Next priorities

1. pass the full Python 3.11 / 3.12 CI on the v0.3 branch
2. real LM Studio + Qwen smoke
3. real Codex `wire_api = "chat"` smoke
4. add `/v1/responses` compatibility
5. Responses streaming + tool event translation
6. per-client/session continuity metadata
7. exact usage accounting / token-aware augmentation budgeting
8. base Qwen vs `Codex + YiSang(Qwen)` benchmark
9. BIO `MemoryPort` adapter later

## Definition of done for v0.3 first milestone

- Codex can select `yisang-qwen` as a custom model
- YiSang injects memory/E.G.O context before Qwen inference
- Codex tool schemas reach Qwen
- Qwen tool calls reach Codex unchanged
- both streaming and non-streaming Chat Completions work
- the model server remains loopback-only by default
- the inherited YiSang test suite still passes
