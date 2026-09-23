# Next Axis — v0.8 Goal / Recovery Runtime

> Proposed start after v0.7/E.G.O closeout integration

## Why this is the next axis

YiSang can now preserve identity, memory, Library knowledge, learned
capabilities, capability lifecycle, and execution policy.

The next missing persistence layer is **ongoing work itself**.

A persistent agent should survive interruption without:

- forgetting what it was doing;
- repeating already-completed irreversible actions;
- losing blockers or partial results;
- restarting a long task from zero.

## Primary objective

~~~text
Goal
  -> Plan / milestones
  -> RunJournal
  -> Action receipts
  -> Checkpoint
  -> interruption
  -> restore
  -> reconcile completed work
  -> resume next safe action
~~~

## Phase 1 — Goal model

Introduce an authoritative GoalPort with:

- goal_id
- description
- state: planned / active / blocked / completed / cancelled
- milestones
- completed_work
- blockers
- next_action
- exit_condition
- attempt / time / token / failure budgets
- created_at / updated_at
- provenance

## Phase 2 — Run journal

Persist append-only run events:

- goal started
- step planned
- action proposed
- action authorized
- action executed
- verification result
- checkpoint written
- blocker detected
- goal completed

The journal is evidence, not model memory.

## Phase 3 — Side-effect receipts

Every externally meaningful mutation should eventually have an idempotency /
receipt identity so recovery can answer:

> Did this already happen before the crash?

Initial targets:

- filesystem write
- git mutation
- process execution with output artifact
- network mutation when later enabled

## Phase 4 — Checkpoint / recovery

On restart:

1. load goal;
2. load latest checkpoint;
3. replay journal metadata;
4. inspect side-effect receipts;
5. validate current environment;
6. reconstruct next safe action;
7. do not repeat completed irreversible effects.

## Phase 5 — Recovery evaluation

Create deterministic crash/restart tests:

- crash before action;
- crash after action but before verification;
- crash after verification but before checkpoint;
- crash after checkpoint;
- resume blocked goal;
- cancelled goal must not resume;
- completed side effect must not duplicate.

## Supporting track — policy-backed real side effects

The permission engine is ready to guard concrete side-effect tools. Add them
only as v0.8 needs them.

Suggested order:

1. filesystem.write inside workspace
2. git status/read operations
3. git local mutation
4. process.spawn with allowlist/resource limits
5. network operations last

## BIO

BIO is explicitly out of scope for v0.8 foundation. The MemoryProvider slot is
reserved and must not become a dependency.

## First implementation slice

Recommended first PR:

~~~text
Goal model
+ GoalPort
+ InMemoryGoalPort
+ SQLiteGoalPort
+ append-only RunJournalPort
+ deterministic restart smoke
~~~

Do not start with autonomous planning. Start with durable state and recovery
semantics.
