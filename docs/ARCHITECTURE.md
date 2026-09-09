# YiSang v0.2 Architecture

## Definition

YiSang is a model-independent enhancement layer around replaceable reasoning
engines.

```text
Identity + Memory + E.G.O + Context + Verification
                         |
                         v
                 Replaceable Engine
```

## Runtime flow

```text
request
 -> retrieve memory
 -> route E.G.O
 -> compile budgeted context
 -> call engine
 -> verify
 -> propose memory
 -> governance
 -> commit
 -> response
```

## Source of truth

- Identity: YiSang identity store
- Memory: `MemoryPort`
- Capability: E.G.O Registry
- Runtime state: YiSang AgentState
- Reasoning: current Engine
- Verification: verifier output

An LLM output is never a source of truth by itself.

## Memory boundary

Core sees only:

```python
MemoryPort.search()
MemoryPort.commit()
MemoryPort.all()
```

v0.2 ships `SQLiteMemoryPort` as a standalone backend. BIO should later be
connected by implementing the same boundary rather than being imported into
Core.

## Engine boundary

A normal model implements `LLMEngine.generate(context)`.

v0.2 ships:

- deterministic demo engine
- `OpenAICompatibleEngine`

The OpenAI-compatible adapter provides a practical route to local models while
keeping provider code outside Core.

Codex is intentionally deferred because it has its own agent loop and should be
represented by a separate `AgentBackend` contract rather than forced into the
single-call LLM interface.

## E.G.O boundary

E.G.O remains external capability metadata:

```text
ego/<name>/
  manifest.json
  SKILL.md
```

`EgoRegistry.from_directory()` loads these assets independently from the
reasoning engine.

## Context compiler

The compiler uses provider-neutral character budgets. It limits:

- user request
- memory count and size
- E.G.O count and instruction size
- final context pack size

A future engine adapter may add exact token-aware budgeting without changing the
core data contract.

## Model invariance

`yisang.eval.invariance` captures:

- agent identity
- durable memory digest
- E.G.O identifiers

Swapping engines should preserve all three.
