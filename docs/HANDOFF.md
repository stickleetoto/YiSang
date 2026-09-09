# YiSang Handoff

## Current target

**v0.2.0 — Standalone Persistence, Local Engine & Guarded Execution**

## Core thesis

YiSang is not an LLM. It is a model-independent enhancement layer.

```text
replaceable reasoning engine
+
persistent external memory
+
portable external capability
+
guarded tool execution
+
verification/governance
```

## v0.2 additions

- SQLite persistent `MemoryPort`
- OpenAI-compatible engine adapter
- context budget policy and deterministic renderer
- E.G.O directory loader
- model invariance probe
- typed `ToolRegistry`
- `ActionProposal` / `ActionDecision` / `ActionResult`
- E.G.O capability + permission `ActionGate`
- side-effect tools disabled by default
- guarded `ActionRuntime`
- action evidence attached before verification
- expanded tests
- correct `.gitignore`

## Guardrails

- BIO is not a dependency yet.
- Do not make model output authoritative.
- Do not let engines write durable memory directly.
- Do not let engines execute tools directly.
- Do not put provider logic in Core.
- Keep E.G.O portable between engines.
- Side-effecting tools remain opt-in.
- Codex should eventually use a dedicated `AgentBackend`.

## Validation status

- previous v0.2 foundation validation: 14 tests passed before this execution patch
- guarded execution patch: 9 focused tests passed in an isolated local harness
- full `dev/v0.2.0` suite should be rerun after pulling this branch

## Next priorities

1. verifier implementations that consume action evidence
2. structured action decoding for OpenAI-compatible engines
3. Codex `AgentBackend` contract and adapter
4. read-only repository tools
5. explicit side-effect approval policy for write tools
6. Qwen/local benchmark harness
7. enhancement benchmark: base model vs YiSang-wrapped model
8. BIO adapter later

## Definition of done for v0.2

- all tests pass
- SQLite memory survives reopening
- local OpenAI-compatible engine can be registered
- E.G.O loads from disk
- budgeted context cannot grow without bound
- identity/memory/capabilities survive engine swap
- model-proposed tools cannot bypass Action Gate
- denied/failed actions remain structured and auditable
