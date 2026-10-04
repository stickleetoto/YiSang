# YiSang v0.7 — Experience Promotion Foundation

## Goal

Build the first safe path from verified experience to reusable capability
without allowing raw model output, raw conversations, or one-off successes to
become durable knowledge.

The first v0.7 slice promotes only Roland Library Usage Notes. Usage Notes are
bounded, inspectable Library data; they are not tool authority and they are not
model weights.

## Flow

~~~text
task / episode
    |
    v
proposed lesson
    |
    v
ExperienceObservation
    |
    +-- evidence_id
    +-- verification_ref
    +-- outcome
    +-- risk_class
    |
    v
ExperiencePort
    |
    v
distinct verified evidence aggregation
    |
    +-- duplicate evidence rejected
    +-- failures force needs_review
    +-- privileged/security-sensitive lessons never auto-promote
    |
    v
promotion threshold (default: 3 successes)
    |
    v
existing Roland KnowledgeEntry
    |
    v
LibraryUsageNote
~~~

## Design references

This slice borrows only the parts that fit YiSang's invariants:

- Reflexion: use task feedback as reusable verbal experience without changing
  model weights.
- Voyager: keep learned capability outside the replaceable base model in a
  reusable library.
- Experiential Reflective Learning: prefer compact transferable heuristics over
  replaying entire trajectories.
- Roland Library: require repeated distinct verified successes before a Usage
  Note becomes durable.

YiSang adds stricter governance:

1. an observation is evidence, not capability;
2. a verified observation requires a verification reference;
3. one evidence ID can count only once for one candidate;
4. failure evidence blocks automatic promotion and requires review;
5. privileged or security-sensitive candidates cannot auto-promote;
6. promotion may update only an existing Library target;
7. the model cannot invent a new Book or KnowledgeEntry through this path.

## New package

~~~text
src/yisang/experience/
  models.py
  port.py
  in_memory.py
  sqlite.py
  promotion.py
~~~

### ExperienceObservation

Represents one task outcome tied to a proposed transferable lesson. It is
intentionally separate from durable Memory and Library data.

### ExperienceCandidate

Aggregates distinct evidence for one normalized lesson and target pair.

Candidate identity is deterministic from:

- target Book;
- target KnowledgeEntry;
- normalized lesson;
- applies_when.

### ExperiencePort

Authoritative pre-promotion store.

Implementations:

- InMemoryExperiencePort for tests and short-lived runs;
- SQLiteExperiencePort for restart-safe candidate accumulation.

### ExperiencePromotionEngine

Default promotion threshold: three distinct verified successes.

When the gate passes it writes or reinforces a LibraryUsageNote on an existing
KnowledgeEntry.

## Safety behavior

### Unverified observation

Rejected and not persisted.

### Duplicate evidence

Returned as duplicate. Counters do not increase.

### Failure evidence

Candidate becomes needs_review. Later successes do not silently erase the
failure or auto-promote it.

### Privileged or security-sensitive lesson

Candidate is retained as blocked, but no automatic durable capability change
occurs.

### Missing Library target

Candidate is retained as blocked. YiSang does not invent a new knowledge target
just to make promotion succeed.

## Persistence

Pre-promotion evidence can span process restarts through SQLiteExperiencePort.

This closes one gap between v0.6 continuity and v0.7 learning: YiSang can
accumulate promotion evidence durably without prematurely turning it into
trusted knowledge.

## Current non-goals

This foundation does not yet:

- generate lessons automatically from raw trajectories;
- modify E.G.O instructions;
- create new E.G.O capabilities;
- promote failure-derived warnings automatically;
- run replay tests itself;
- connect promotion directly to every Runtime request;
- give promoted knowledge execution authority.

## Next slices

1. deterministic episode and trajectory record contract;
2. validator and replay adapter so promotion can require reproducible tests;
3. failure to anti-pattern candidate to validated warning path;
4. Runtime hook that accepts structured lesson proposals while keeping the
   ExperiencePromotionEngine authoritative;
5. promotion audit and rollback;
6. benchmark promotion precision, false-promotion rate, replay pass rate, and
   downstream task improvement.
