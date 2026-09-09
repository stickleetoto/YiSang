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
 -> collect ActionProposal objects
 -> Action Gate checks tool + E.G.O capability + permissions
 -> Action Runtime executes only authorized tools
 -> attach action evidence to EngineResult metadata
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
- Tool authority: YiSang Action Gate
- Reasoning: current Engine
- Verification: verifier output

An LLM output is never a source of truth or execution authority by itself.

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

## Execution boundary

An engine may only *propose* an action:

```text
EngineResult.action_proposals
        |
        v
ActionGate
  - tool exists?
  - selected E.G.O provides required capabilities?
  - E.G.O permissions satisfy tool requirements?
  - side effects explicitly enabled?
        |
        v
ActionRuntime
        |
        v
ActionResult
        |
        v
ActionEvidenceVerifier / CompositeVerifier
```

Important invariants:

1. tool ids emitted by a model do not grant execution authority;
2. every registered tool requires at least one E.G.O capability;
3. unknown tools are denied;
4. insufficient permissions are denied;
5. side-effecting tools are disabled by default;
6. tool exceptions become structured `ERROR` results instead of crashing the
   YiSang runtime;
7. action evidence is attached before verification;
8. failed action evidence can prevent unsupported memory promotion.

The current filesystem permission ordering is:

```text
none < read < workspace < unrestricted
```

See `docs/EXECUTION.md` for the concrete execution contract.

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
