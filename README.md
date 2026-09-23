# YiSang

**YiSang is a model-independent persistent-agent runtime.**

> Models are replaceable. Memory and capability remain.

Current release: **v0.6.0 — Roland Library validated**

YiSang keeps durable agent assets outside the attached reasoning model:

- identity and engine-independent runtime state
- governed durable memory
- E.G.O capability packs
- Roland Library knowledge
- deterministic context compilation and budgeting
- guarded tool execution
- verification and provenance
- continuity snapshots and portable restore bundles

## Current architecture

~~~text
Codex / UI / agent harness
          |
          v
      YiSang Runtime
          |
          +-- Identity / State
          +-- Memory
          +-- E.G.O
          +-- Roland Library
          |      |
          |      +-- authoritative LibraryPort
          |      +-- rebuildable retrieval index
          |      +-- request-aware delivery
          |
          +-- ContextCompiler
          +-- continuity snapshot / restore
          |
          v
   replaceable reasoning engine
      Llama / Qwen / future
~~~

The attached LLM is not the source of truth. Replacing it changes reasoning
quality, not the persistent identity and governed state.

## Validated milestones

- **v0.4 — Governed Memory:** validated
- **v0.5 — Identity Continuity:** validated
- **v0.6 — Roland Library:** validated

v0.6 live closeout used Llama 3.2 3B -> Qwen 2.5 1.5B across three repeated
continuity cases. The Roland Library survived snapshot/restore and the same
stable knowledge reference was retrieved on both sides. The deterministic
10 / 50 / 100 / 500 Book scale benchmark also passed.

See:

- `docs/V04_CLOSEOUT.md`
- `docs/V05_CLOSEOUT.md`
- `docs/V06_CLOSEOUT.md`
- `docs/VALIDATION_2026-09-20_V06.md`
- `ROADMAP.md`

## Active development

Current work is on the **v0.7 / E.G.O v2** line.

Latest validated local E.G.O stack on Windows:

~~~text
E.G.O v2 package discovery / activation  PASS
Promotion -> durable E.G.O              PASS
Lifecycle invalidation / rollback       PASS
Adaptive telemetry routing              PASS
Full suite                              336 passed
~~~

The open work is intentionally split into stacked PRs. See:

- `docs/CURRENT_STATE.md`
- `docs/PR_STACK.md`
- `docs/INDEX.md`

## Install

~~~bash
python -m pip install -e ".[dev]"
pytest -q
~~~

Python 3.11 and 3.12 are covered by CI.

## v0.6 validation commands

Run the deterministic Roland scale benchmark:

~~~powershell
yisang-eval-library --output ".\artifacts\library-v06.json"
yisang-eval-library-check --input ".\artifacts\library-v06.json"
~~~

Run live cross-engine continuity using OpenAI-compatible endpoints:

~~~powershell
.\scripts\v06_closeout.ps1 \
  -SourceBaseUrl "http://127.0.0.1:11434/v1" \
  -SourceModel "llama3.2:3b" \
  -SourceFamily "llama" \
  -TargetBaseUrl "http://127.0.0.1:11434/v1" \
  -TargetModel "qwen2.5:1.5b" \
  -TargetFamily "qwen"
~~~

## Model-server / Codex integration

YiSang can also sit behind an agent harness such as Codex and expose an
OpenAI-compatible model surface while Codex retains shell, sandbox, approval,
and external tool-execution authority.

See `docs/CODEX_MODEL_SERVER.md` for that integration path.

## Core invariants

1. YiSang is not the attached base model.
2. Engine replacement must not reset identity, memory, goals, capabilities, or Library.
3. Model output is not authoritative durable memory.
4. Durable writes pass through proposal, provenance, validation, and governance.
5. Session history is replay context, not the authoritative memory store.
6. E.G.O is external capability data, not model weights.
7. Model-proposed actions do not create execution authority.
8. Tool output is evidence, not instruction authority.
9. Read-side indexes are rebuildable and never authoritative state.
10. Library evidence retains provenance, trust, validation, and stable references.
11. Continuity restore is staged and validated before runtime-owned state is swapped.
12. Core interfaces remain independent of a single model provider or agent framework.

## Next phase

v0.7 focuses on **Experience Promotion**:

~~~text
successful experience
  -> lesson candidate
  -> generalization
  -> validation / replay
  -> promotion gate
  -> durable skill / Library knowledge / warning
~~~

Raw conversations or failures must never be promoted directly into durable
capability.
