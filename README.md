# YiSang

**YiSang is a model-independent LLM enhancement layer.**

> Models are replaceable. Memory and capability remain.

YiSang keeps durable agent assets outside the model:

- identity and runtime state
- external memory
- E.G.O capability packs
- context compilation
- verification and governance

The attached LLM is a replaceable reasoning engine.

## v0.2

v0.2 makes the foundation usable without BIO:

- persistent `SQLiteMemoryPort`
- OpenAI-compatible local LLM engine (e.g. LM Studio)
- model-agnostic context budgets
- deterministic context rendering
- E.G.O loading from `manifest.json` + `SKILL.md`
- engine-swap invariance probe
- no required third-party runtime dependencies

BIO remains a future `MemoryPort` adapter rather than a YiSang dependency.

## Architecture

```text
User / App
    |
    v
YiSang Runtime
    |
    +-- Identity
    +-- MemoryPort -------- SQLite now / BIO later
    +-- E.G.O Registry
    +-- Context Compiler
    +-- Engine Router ----- local LLM / Codex later
    +-- Verifier
    +-- Memory Governor
```

## Install

```bash
python -m pip install -e .[dev]
pytest -q
```

## Demo

```bash
python examples/demo.py
```

## Local Qwen / LM Studio

Start an OpenAI-compatible local server, then register it as an engine:

```python
from yisang.engines.openai_compatible import OpenAICompatibleEngine

engine = OpenAICompatibleEngine(
    engine_id="qwen-local",
    base_url="http://127.0.0.1:1234/v1",
    model="your-loaded-model-id",
)
```

YiSang Core does not depend on LM Studio; any compatible endpoint can implement
the engine role.

## Core invariants

1. `YiSang != LLM`
2. Engine replacement must not reset memory.
3. Engine replacement must not reset capabilities.
4. Model output is not authoritative memory.
5. Memory writes pass through proposal + governance.
6. E.G.O is external capability data, not model weights.
7. Core depends on interfaces, not model providers.

See `docs/ARCHITECTURE.md` and `docs/HANDOFF.md`.
