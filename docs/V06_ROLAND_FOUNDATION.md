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

## Explicitly deferred

The current v0.6 slices do not yet include:

- request-aware delivery
- ContextPack Library payload
- ContextBudgetReport Library accounting
- snapshot / continuity bundle Library restore
- SQLite LibraryPort
- active Usage Note promotion

Usage Note creation/promotion remains a v0.7 Experience Promotion concern.
v0.6 only preserves compatible durable notes during import.

## Next slice

1. add request-aware delivery and safety-preserving budget compression;
2. add Library payload and budget accounting to ContextCompiler;
3. wire optional Library retrieval into YiSangRuntime;
4. make `IdentitySnapshot.library` a real digest/reference;
5. extend continuity bundles with Library archive/restore;
6. port deterministic retrieval and tight-budget safety evals;
7. import private Book packs only through an explicit external path.
