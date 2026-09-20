# YiSang v0.6 Roland Foundation

Status: **active development**

## Migration boundary

The legacy Roland repository is a private source asset. YiSang is public.

v0.6 therefore ports the architecture and generic compatibility code without
copying the private Book corpus into this repository.

Target boundary:

~~~text
Codex / UI
    |
    v
YiSang Runtime
    |
    +-- Memory
    +-- E.G.O
    +-- Roland Library
           |
           +-- authoritative LibraryPort
           +-- derived retrieval indexes
           +-- fit / delivery
           +-- ContextCompiler integration
    |
    v
replaceable LLM
~~~

Roland is a Library subsystem. It does not become a second execution runtime.

## Foundation implemented

### YiSang-native models

`src/yisang/library/models.py` defines:

- `Book`
- `KnowledgeEntry`
- compatibility-only `LibraryUsageNote`
- source references
- trust class
- validation state
- schema versioning

The normal atomic retrieval unit remains `KnowledgeEntry`. A mandatory
Book/Chapter rewrite is intentionally avoided.

### Authoritative storage boundary

`LibraryPort` separates authoritative Book storage from future read-side
indexes.

The first reference implementation is `InMemoryLibraryPort`.

Derived lexical, semantic, vector, and compact indexes must remain rebuildable
and must never become authoritative Library state.

### Archive and digest

The foundation includes a deterministic checksummed archive contract:

- deterministic Book ordering
- archive schema version
- Library schema version
- Book count
- SHA-256 over canonical Book payload
- validation before restore
- non-empty target protection
- explicit overwrite restore

The digest is intended to become the v0.6 `IdentitySnapshot.library`
reference digest later in the phase.

### Legacy Roland importer

The compatibility importer reads the existing Roland `book.json` shape and
maps it to YiSang-native models.

It preserves:

- Book ids / titles / versions
- Knowledge Entry ids
- aliases and tags
- use / avoid conditions
- structure / tradeoffs / complexity
- pitfalls and implementation hints
- already-promoted Usage Notes, if any

Imported file paths are retained as source references unless the source data
already carries explicit `source_refs`.

The importer does not expose or bundle the private Roland Book corpus.

## Second slice: compact lexical retrieval

Implemented:

- rebuildable `CompactLibraryIndex`
- deterministic integer `LeanKnowledgeRef`
- term -> KnowledgeEntry postings
- candidate-only lexical scoring instead of catalog-wide entry scans
- weighted title/alias/tag/summary/use-condition ranking
- `recommended` / `caution` / `avoid` fit judgement
- explicit constraint-conflict evidence
- deterministic tie-breaking
- rebuild semantics after authoritative Library changes

The index is derived entirely from `LibraryPort` and can be discarded and rebuilt.

## Third slice: request-aware delivery

Implemented:

- stable opaque `knowledge_ref`
- `primary` / `complement` / `guardrail` delivery roles
- provenance / trust / validation metadata in model-visible Library evidence
- implementation hints only for implementation-oriented requests
- complexity only for performance-oriented requests
- tradeoffs and pitfalls only when comparison/risk intent requires them
- safety-critical `avoid_when` retained through ordinary pruning
- character-budget compression that drops optional detail before guardrails

## Fourth slice: ContextCompiler and Runtime integration

Implemented:

- `ContextPack.library` model-visible evidence payload
- `ContextBudgetPolicy.max_library_chars` / `max_library_items`
- `ContextBudgetReport` Library character and selection accounting
- deterministic `[ROLAND LIBRARY]` rendering
- optional `LexicalLibraryRetriever` injection into `YiSangRuntime`
- request -> retrieve -> request-aware delivery -> ContextCompiler pipeline
- `YiSangResponse.used_knowledge_refs` based on evidence actually compiled for the model
- global-budget pruning that removes optional Library detail and positive complements before guardrails
- no-Library compatibility path that preserves the prior runtime behavior

## Fifth slice: snapshot and continuity integration

Implemented:

- runtime-owned authoritative `LibraryPort`
- automatic `IdentitySnapshot.library` reference generation from the authoritative Library digest
- `library://authoritative` snapshot reference with Library schema version
- runtime-vs-snapshot Library drift detection
- continuity bundle `library_archive` payload with internal archive checksum validation
- snapshot reference / archive schema / digest consistency checks
- staged Library restore into an empty `LibraryPort`
- post-stage digest verification before runtime mutation
- rollback-safe Runtime Library swap
- automatic `LexicalLibraryRetriever` rebuild after Library restore
- restore evidence for Library book count and pre/post digest
- compatibility with older snapshots where `library=None`

## Sixth slice: continuity retrieval and scale validation harnesses

Implemented:

- continuity probe support for expected `knowledge_ref` values
- source-side and restored-runtime Library retrieval evidence
- explicit `library_preserved` continuity result
- v0.6 closeout gate requiring Library snapshot preservation and source/target knowledge retrieval
- backward-compatible loading of v0.5 continuity reports without Library fields
- `yisang-eval-continuity-check --phase auto|v0.5|v0.6`
- live OpenAI-compatible continuity runner seeded with a deterministic Roland Book
- `yisang-eval-library` deterministic scale benchmark
- default scale matrix: 10 / 50 / 100 / 500 Books
- scale metrics for index build latency, mean/p95 search latency, top-1 selection accuracy, index size, and delivered context size

The v0.6 continuity criterion is stronger than archive equality alone: the
restored Runtime must retrieve the expected stable knowledge reference after
the reasoning engine is replaced.

## Explicitly deferred

The current v0.6 slices do not yet include:

- SQLite LibraryPort
- active Usage Note promotion

Usage Note creation/promotion remains a v0.7 Experience Promotion concern.
v0.6 only preserves compatible durable notes during import.

## Next slice

1. run the live cross-family v0.6 continuity evaluator against the local Llama/Qwen endpoints;
2. run and save the 10 / 50 / 100 / 500 Book scale benchmark report;
3. add tighter end-to-end safety-budget cases around primary/guardrail competition;
4. import private Book packs only through an explicit external path;
5. close v0.6 only after the saved continuity and scale reports are reproducible;
6. keep SQLite LibraryPort deferred until persistence pressure justifies it.
