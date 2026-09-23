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


## Session 2026-09-20 / GPT-5.6 Sol / v0.7 durable promotion + apply boundary

- Goal:
  - make accepted promotion artifacts durable and introduce an explicit governed
    application boundary
- Added:
  - PromotionPort abstraction
  - SQLitePromotionPort with persistent artifacts and apply receipts
  - application requests carrying actor, approval_ref, reason, and target_ref
  - idempotent LibraryKnowledgeApplyAdapter
  - stable promoted Library entry ids and promotion provenance
  - EgoInstructionPatchAdapter that produces an approved patch without mutating
    the current file-backed E.G.O registry
  - persistent invalidation and application receipt tests
- Important boundary:
  - validation/promotion and application remain separate operations
  - E.G.O is not directly mutated until it has its own durable mutation port
  - repeated Library application cannot duplicate the same promoted entry
- Next:
  - durable E.G.O mutation/version port
  - runtime episode capture and replay harness integration
  - promotion rollback/supersession across applied targets


## Session 2026-09-20 / GPT-5.6 Sol / v0.7 runtime episode capture
- Added ExperiencePort with in-memory and SQLite stores.
- YiSangRuntime can optionally capture normalized success/failure episodes.
- Raw request text is fingerprinted with SHA-256 instead of copied into normalized metadata.
- Only explicitly goal-satisfied executed tool results become promotable tool evidence.
- Added yisang-experience-smoke and yisang-experience-audit for local verification.
- Capture remains separate from candidate creation and promotion/application.


## Session 2026-09-20 / GPT-5.6 Sol / v0.7 deterministic generalization + replay plan

- Added ExperienceGeneralizer with a conservative repeated-evidence threshold.
- Procedure candidates require repeated success, promotable evidence in every source episode, at least one shared trigger, and identical procedure steps.
- Warning candidates require repeated failure evidence.
- Candidate ids are content-derived and deterministic across source ordering.
- Added source-episode ReplayPlan and strict ReplayReport construction.
- Replay report creation rejects missing or unexpected test results.
- Added yisang-generalization-smoke for local Episode -> Candidate -> ReplayPlan -> PromotionGate wiring.
- Important: the smoke uses simulated replay results; real tool replay remains a later v0.7 slice.


## Session 2026-09-20 / GPT-5.6 Sol / v0.7 deterministic replay executor

- Added DeterministicReplayExecutor.
- Replay execution uses explicit argv with shell=False.
- Every executable must be explicitly allowlisted by the caller.
- Each replay runs in its own temporary workspace.
- Setup/expectation paths reject absolute paths and parent-directory traversal.
- Deterministic checks currently support exit code, stdout/stderr containment,
  file existence, and exact UTF-8 file content.
- Timeout and OS execution failures become failed ReplayCaseResult records.
- Every executed replay emits a SHA-256 observation evidence reference.
- Added yisang-real-replay-smoke: three subprocess replays -> ReplayReport ->
  PromotionGate.
- This proves real deterministic replay execution; mapping arbitrary historical
  tool traces into replay manifests remains a separate integration step.


## Session 2026-09-20 / GPT-5.6 Sol / v0.7 trace-to-replay compiler

- Added runtime ActionTrace capture with in-memory and SQLite ports.
- Runtime tool arguments are fingerprinted; raw argument values are not stored
  in ActionTrace.
- Replay manifests are accepted only from completion_evidence.replay_manifest on
  EXECUTED + goal_satisfied tool results.
- Malformed or unverified manifests are retained only as rejected trace
  metadata and cannot become replay specs.
- Added ReplayManifestCompiler from source episode request ids + ActionTracePort
  to ReplayExecutionSpec.
- v1 compiler intentionally supports exactly one replayable tool step per case;
  multi-tool traces are rejected until an ordered multi-step executor contract
  exists.
- Added yisang-trace-replay-smoke for Trace -> Manifest -> real replay ->
  PromotionGate.


## Session 2026-09-23 / GPT-5.6 Sol / E.G.O v2 foundation

- Researched Agent Skills progressive disclosure, A2A AgentSkill discovery,
  JSON Schema 2020-12, MCP-style risk hints, Cedar authorization concepts,
  OCI artifact packaging, and Sigstore signing.
- Added E.G.O v2 capability-package architecture document.
- Preserved legacy E.G.O v1 model/loader behavior.
- Added metadata-only v2 package discovery and selected-package full loading.
- Added safe package path enforcement and content SHA-256 package digest.
- Added input/output JSON Schema loading with 2020-12 dialect guard.
- Added semantic-version-aware lazy VersionedEgoRegistry.
- Added A2A AgentSkill-shaped discovery export.
- Added deterministic HybridCapabilityRouter using metadata and bounded success
  priors; embeddings remain a later implementation.
- V2 capability metadata now participates in E.G.O continuity digest without
  changing v1 digest serialization.


- Progressive v2 discovery now computes the immutable package SHA-256 without
  placing detailed SKILL/schema content into model context.
- E.G.O continuity serialization for v2 binds the package digest and metadata,
  not transient progressive-loading state, so metadata -> full activation does
  not change the capability continuity digest.
- Added yisang-ego-v2-smoke and focused local validation instructions.


## Session 2026-09-23 / GPT-5.6 Sol / durable E.G.O promotion apply

- Added EgoPort authoritative installation-state boundary.
- Added InMemoryEgoPort and SQLiteEgoPort.
- Added active/disabled/superseded lifecycle, automatic supersession, disable,
  and rollback to an already-installed version.
- Added deterministic PromotionArtifact -> EgoManifest v2 prompt package builder.
- Integer promotion versions normalize to semantic 0.0.N versions.
- Generated package digests bind manifest content and promotion provenance.
- Added DurableEgoApplyAdapter with explicit approval and promotion receipt
  idempotence.
- Added DurableEgoRegistryView exposing only active durable packages to existing
  runtime/router contracts.
- Added yisang-ego-promotion-smoke proving apply -> supersede -> route ->
  rollback.
