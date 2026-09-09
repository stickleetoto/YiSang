# YiSang v0.1 Handoff

## Current baseline

Foundation scaffold.

## Goal

Build a model-independent LLM enhancement layer where memory and capability survive engine swaps.

## Implemented

- Core runtime
- Identity charter / state
- Memory interface
- In-memory memory backend
- Proposal governance
- E.G.O registry and router
- Context compiler
- Engine interface/router
- Demo deterministic engines
- Verification contract
- Baseline tests

## Next priorities

1. BIO MemoryPort adapter
2. Codex AgentBackend adapter
3. persistent SQLite backend
4. real tool/action gate
5. benchmark harness
6. Qwen local backend
7. context budget hardening

## Guardrails

- Do not make any model the source of truth.
- Do not let engines write memory directly.
- Do not couple Core to BIO internals.
- Do not couple Core to Codex implementation.
- Preserve portability between engines.
