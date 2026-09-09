# YiSang Handoff

## Current target

**v0.2.0 — Standalone Persistence & Local Engine**

## Core thesis

YiSang is not an LLM. It is a model-independent enhancement layer.

```text
replaceable reasoning engine
+
persistent external memory
+
portable external capability
+
verification/governance
```

## v0.2 additions

- SQLite persistent `MemoryPort`
- OpenAI-compatible engine adapter
- context budget policy and deterministic renderer
- E.G.O directory loader
- model invariance probe
- expanded tests
- correct `.gitignore`

## Guardrails

- BIO is not a dependency yet.
- Do not make model output authoritative.
- Do not let engines write durable memory directly.
- Do not put provider logic in Core.
- Keep E.G.O portable between engines.
- Codex should eventually use a dedicated `AgentBackend`.

## Next priorities

1. Action Gate + typed Tool Registry
2. actual verifier implementations
3. Codex `AgentBackend`
4. Qwen/local benchmark harness
5. enhancement benchmark: base model vs YiSang-wrapped model
6. BIO adapter later

## Definition of done for v0.2

- all tests pass
- SQLite memory survives reopening
- local OpenAI-compatible engine can be registered
- E.G.O loads from disk
- budgeted context cannot grow without bound
- identity/memory/capabilities survive engine swap
