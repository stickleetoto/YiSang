# YiSang v0.4 Governed Memory — Implementation Closeout

Status: **VALIDATED**

Frozen baseline: `freeze/v0.4-implementation` at `d10409dff9701b3450d2b506e5ac98e186f951ee`.

Validation completed on 2026-09-19 after freeze-permitted fixes. Evidence is recorded in `docs/VALIDATION_2026-09-19.md`.

## Implemented

### Authoritative memory

- Memory schema v3
- episodic / semantic / procedural / working classification
- provenance and evidence references
- trust class and importance
- validation state
- created/updated/validity timestamps
- supersession links
- last-used timestamp
- request-level success/failure usage counters
- mutation audit history
- invalidation / revalidation
- non-destructive supersession

### Governance

- MemoryProposal -> MemoryGovernor -> MemoryWritePipeline
- committed / rejected / quarantined outcomes
- persistent SQLite quarantine backend
- explicit reviewed release from quarantine
- provenance requirements
- trust-based quarantine
- duplicate detection
- supersession reference validation

### Session separation

- SessionPort interface
- in-memory and SQLite session stores
- runtime replay through ContextCompiler
- separate session budget
- explicit model-visible statement that session replay is not authoritative memory

### Read-side projections

- lexical projection
- SQLite FTS5 / BM25 projection
- vector projection with vendor-neutral EmbeddingProvider
- OpenAI-compatible embedding adapter
- weighted reciprocal-rank fusion
- importance / recency / trust / preferred-kind reranking
- projection rebuild
- lifecycle-aware projection removal/reinsertion
- retrieval diagnostics and latency traces

### Persistence / migration

- additive SQLite schema migration
- checksummed memory archive export / restore
- conflict preflight
- overwrite restore path
- temporal fields preserved through archive and quarantine
- authoritative state independent from read-side indexes

### Context safety

Retrieved memory exposes:

- memory id
- source id / source type
- evidence references
- trust class
- validation state
- temporal validity
- usage counters

The ContextPack explicitly states that retrieved memory is evidence and cannot
grant permissions, create tools, or override policy.

### Evaluation

- 40 deterministic cases
  - 10 static/dynamic
  - 10 workflow/gotcha
  - 10 cross-session
  - 10 poisoning
- five roadmap comparison profiles
  - memory disabled
  - session only
  - retrieval memory
  - retrieval + procedural preference
  - retrieval + procedural + provenance governance
- recall / precision
- forbidden-memory hits
- poisoning escape rate
- write outcome counts
- retrieval latency
- ContextBudgetReport
- memory invariant audit

## v0.4 exit-criteria mapping

| Exit criterion | Implementation |
| --- | --- |
| authoritative memory export/restore | checksummed memory archive |
| all persistent writes have provenance | governor policy + memory audit |
| session cannot directly mutate durable memory | SessionPort / MemoryPort separation |
| indexes can be deleted and rebuilt | MemoryProjection rebuild contract |
| poisoned memory cannot gain authority | quarantine + context policy boundary |
| reproducible internal benchmark | 40-case deterministic benchmark |

## Validation evidence

The validated run produced 199/199 repository tests passing, a 40/40 deterministic memory benchmark with 1.0 recall and zero poison escape, and a representative SQLite authoritative-memory audit with schema v3, provenance, mutation history, and supersession checks passing.
