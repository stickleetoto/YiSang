# YiSang v0.1

YiSang is a **model-independent LLM enhancement layer**.

Core principle:

> Models are replaceable. Memory and capability remain.

YiSang separates:

- Identity
- Memory
- E.G.O / Skills
- Context compilation
- Engine backends
- Verification
- Governance

The LLM is treated as a replaceable reasoning engine.

## Architecture

```text
User
 ↓
YiSang Runtime
 ├ Identity
 ├ MemoryPort
 ├ E.G.O Registry
 ├ Context Compiler
 ├ Engine Router
 ├ Verification
 └ Memory Governance
      ↓
  LLM / Agent Backend
```

## Quick start

```bash
python -m pip install -e .[dev]
pytest -q
python examples/demo.py
```

## v0.1 scope

Implemented:

- YiSang core runtime
- immutable-ish identity charter object
- in-memory memory backend
- MemoryProposal + governance gate
- E.G.O manifest / registry / routing
- ContextPack compiler
- generic LLMEngine interface
- deterministic demo engine
- verification result contract
- model invariance smoke test
- enhancement smoke test

Not implemented yet:

- BIO adapter
- Codex adapter
- persistent DB backend
- real embeddings
- tool execution sandbox
- LoRA / fine-tuning
