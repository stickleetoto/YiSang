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

## Active next phase: v0.7 Experience Promotion

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

## Post-freeze measurement fix

The validated v0.6 freeze preserves the exact binary that produced the recorded
closeout evidence. Mainline development then corrected the small-sample
percentile estimator to nearest-rank semantics and added regression tests.

This measurement-only fix begins the `0.6.1.dev0` line. It does not alter the
v0.6 continuity/Library pass criteria or mutate the validated/freeze branches.

## Development rule

Do not advance a phase because code merely exists. Preserve tests, saved
evidence, exit criteria, and explicit migration boundaries.


## Session 2026-09-20 / GPT-5.6 Sol / v0.7 experience foundation

- Goal:
  - begin v0.7 with a deterministic, side-effect-free Experience Promotion gate
- Added:
  - `yisang.experience` domain models
  - verified evidence classification
  - replay-completeness and replay-failure checks
  - automatic-promotion block for privileged/security-sensitive candidates
  - candidate-kind to target boundary checks
  - versioned `PromotionArtifact`
  - in-memory promotion ledger with invalidation
  - focused v0.7 tests and design note
- Important boundary:
  - promotion eligibility does not directly mutate E.G.O or Roland Library
  - raw conversation/model claims may remain provenance but cannot independently
    satisfy promotion evidence
- Next:
  - durable PromotionPort
  - governed application adapters for E.G.O / Library / warnings / routing
  - replay harness integration with real runtime episodes
