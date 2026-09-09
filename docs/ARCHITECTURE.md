# YiSang v0.1 Architecture

## Invariants

1. `YiSang != LLM`
2. Engine replacement must not reset memory.
3. Engine replacement must not reset capabilities.
4. LLM output is not authoritative memory.
5. Memory writes go through proposals and governance.
6. E.G.O is external capability metadata, not model weights.
7. Core code depends on interfaces, not specific model providers.

## Runtime flow

```text
request
 -> retrieve memory
 -> route E.G.O
 -> compile context
 -> call engine
 -> verify
 -> propose memory
 -> governance
 -> commit
 -> response
```

## Source of truth

- Identity: YiSang identity store
- Memory: MemoryPort implementation
- Capability: E.G.O Registry
- Runtime state: YiSang AgentState
- Reasoning: current Engine
- Verification: verifier output
