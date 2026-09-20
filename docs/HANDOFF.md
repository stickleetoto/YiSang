# YiSang Handoff

## Current release

**v0.6.0 — Roland Library validated**

v0.4 Governed Memory, v0.5 Identity Continuity, and v0.6 Roland Library have
all crossed their validation gates.

Latest validation evidence:

- live source model: `llama3.2:3b`
- live target model: `qwen2.5:1.5b`
- engine families: Llama -> Qwen
- continuity repeats: 3
- continuity pass rate: 1.0
- Library knowledge-ref retrieval before/after restore: passed
- 10 / 50 / 100 / 500 Book benchmark: passed
- composite v0.6 closeout: `ready=true`

See `docs/VALIDATION_2026-09-20_V06.md`.

## Core thesis

~~~text
Models are replaceable.
Memory and capability remain.
~~~

YiSang owns persistent cognition/state. The attached LLM is a replaceable
reasoning engine.

## Current runtime boundary

~~~text
Codex / client / UI
        |
        v
YiSang Runtime
        |
        +-- Identity / State
        +-- governed Memory
        +-- E.G.O capability registry
        +-- Roland Library
        |      +-- authoritative LibraryPort
        |      +-- CompactLibraryIndex
        |      +-- retrieval / fit / delivery
        +-- ContextCompiler
        +-- continuity snapshot / bundle / restore
        |
        v
replaceable Llama / Qwen / future engine
~~~

## v0.6 implemented

- YiSang-native `Book` and `KnowledgeEntry`
- authoritative `LibraryPort`
- deterministic checksummed Library archive/digest
- legacy Roland importer without copying the private corpus into the public repo
- compact deterministic lexical retrieval
- request-aware primary / complement / guardrail delivery
- stable `knowledge_ref`
- provenance / trust / validation in model-visible evidence
- Library-aware ContextPack and budget accounting
- optional Runtime retrieval integration
- authoritative Runtime Library ownership
- IdentitySnapshot Library digest binding
- portable continuity-bundle Library archive/restore
- staged Library restore before runtime mutation
- retriever rebuild after restore
- v0.6 continuity evaluator with source/target knowledge-ref proof
- 10 / 50 / 100 / 500 Book benchmark
- severe-budget guardrail priority
- saved evidence checkers and composite closeout gate

## Public/private boundary

The legacy Roland repository and private Book corpus remain private source
assets.

The public YiSang repository may contain:

- generic Library architecture
- schemas/interfaces
- import compatibility code
- synthetic fixtures
- benchmark data

It must not contain the private Roland Book corpus.

## Validated branches

Expected preserved validation/freeze branches after closeout:

- `freeze/v0.4-implementation`
- `validated/v0.5`
- `freeze/v0.5-implementation`
- `validated/v0.6`
- `freeze/v0.6-implementation`

## Immediate next phase: v0.7 Experience Promotion

Target pipeline:

~~~text
Raw Episode
    |
    v
Lesson Candidate
    |
    v
Generalize
    |
    v
Validator
    |
    v
Replay / test
    |
    v
Promotion Gate
    |
    v
Durable Skill / Knowledge / Warning
~~~

Rules:

- raw conversation text is never promoted directly;
- failure is evidence, not a skill;
- every promoted artifact carries source evidence;
- promotion must be replayable/testable;
- privileged or security-sensitive capability is not auto-promoted;
- promoted capability must be invalidatable and versioned;
- Roland Library may receive validated knowledge, but v0.7 owns the promotion logic.

## Known follow-up

The v0.6 validation binary used a simple percentile estimator that is weak for
three-sample p95 reporting. The closeout gates do not depend on latency
thresholds. Correct the small-sample percentile estimator after the validated
v0.6 freeze so the exact validated runtime boundary remains preserved.

## Development rule

Do not advance a phase because code merely exists. Preserve tests, saved
evidence, exit criteria, and explicit migration boundaries.
