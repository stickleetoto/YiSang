# YiSang Handoff

## Current target

**v0.2 development — Standalone Persistence, Local Engine & Guarded Tool Loop**

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
bounded tool feedback
+
verification/governance
```

## Implemented in the current development branch

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
- `ActionEvidenceVerifier`
- `CompositeVerifier`
- failed/denied actions can block memory commit
- structured JSON action decoding
- OpenAI-style native `tool_calls` decoding
- authorized tool surface in `ContextPack`
- bounded action-feedback loop
- read-only workspace list/read tools
- workspace path escape protection
- lightweight argument-schema validation
- GitHub Actions pytest matrix for Python 3.11 / 3.12

## Guardrails

- BIO is not a dependency yet.
- Do not make model output authoritative.
- Do not let engines write durable memory directly.
- Do not let engines execute tools directly.
- Do not put provider logic in Core.
- Keep E.G.O portable between engines.
- Side-effecting tools remain opt-in.
- Tool outputs are untrusted data/evidence.
- Tool loops must remain bounded.
- Failed deterministic actions must not become remembered successes.
- Codex should eventually use a dedicated `AgentBackend`.

## Validation status

- v0.2 foundation: 14 tests passed before guarded execution work
- guarded execution/action-verification milestone: 13 focused tests passed
- structured action + tool-feedback + workspace-read milestone: focused local harness passed
- GitHub Actions full suite: **PASS** on Python 3.11 and 3.12 (run 34319460691)

## Next priorities

1. real LM Studio / Qwen smoke with `workspace.list` and `workspace.read_text`
2. Codex `AgentBackend` contract
3. explicit side-effect approval policy for write tools
4. domain-specific verifier policies
5. Qwen/local enhancement benchmark
6. base model vs YiSang-wrapped model benchmark
7. BIO adapter later

## Definition of done for this line

- all tests pass
- SQLite memory survives reopening
- local OpenAI-compatible engine can be registered
- E.G.O loads from disk
- budgeted context cannot grow without bound
- identity/memory/capabilities survive engine swap
- model-proposed tools cannot bypass Action Gate
- denied/failed actions remain structured and auditable
- failed action evidence can prevent memory promotion
- compatible engines can consume tool results and produce a final answer
- read-only workspace tools cannot escape their configured root
