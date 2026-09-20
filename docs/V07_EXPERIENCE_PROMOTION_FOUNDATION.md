# YiSang v0.7 — Experience Promotion Foundation

## Status

Initial v0.7 implementation slice.

This slice establishes the deterministic promotion boundary. It does **not**
apply promoted artifacts to E.G.O or the Roland Library yet.

## Pipeline boundary

~~~text
normalized episode evidence
        |
        v
LessonCandidate
        |
        v
ReplayReport
        |
        v
PromotionGate
        |
        +-- reject
        |
        +-- PromotionArtifact
                |
                v
        PromotionLedger
~~~

A later integration slice may apply accepted artifacts to E.G.O, Library
knowledge, durable warnings, or routing heuristics through their own governed
mutation boundaries.

## Enforced invariants

- raw conversation evidence alone cannot pass promotion;
- at least one verified promotable evidence source is required;
- declared validation tests must all be present in the replay report;
- any failed declared replay blocks promotion;
- replay evidence must belong to the same candidate;
- privileged and security-sensitive candidates cannot be auto-promoted;
- procedure/knowledge candidates require successful experience;
- warning candidates require failure evidence;
- candidate kind limits the allowed promotion target;
- successful promotion produces a versioned, inspectable artifact rather than
  directly mutating E.G.O or Library state;
- promoted artifacts can be invalidated while remaining auditable.

## Evidence classes

Raw conversation and model claims may be retained as provenance, but they do
not count as promotable verification by themselves.

Promotable verified evidence currently includes:

- tool results
- test results
- explicit user confirmation
- governed durable memory
- Roland Library references

## Next slice

The next implementation should add a durable PromotionPort and explicit
application adapters:

~~~text
PromotionArtifact
  -> PromotionPort
  -> governed apply adapter
       +-- E.G.O refinement
       +-- Library knowledge
       +-- durable warning
       +-- routing heuristic
~~~

Applying an artifact must remain separate from deciding that the artifact is
eligible for promotion.
