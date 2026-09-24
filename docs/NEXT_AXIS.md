# Development Axis Status

> Updated: 2026-09-24

## v0.8 — Goal / Recovery Runtime

Foundation implementation now spans PR #66 through #69.

Core path:

~~~text
Goal
-> RunJournal
-> Action receipt
-> checkpoint
-> crash/restart
-> reconcile external side effect
-> resume safely
~~~

The first real side effect is workspace.write_text with atomic file replacement,
policy integration, idempotency receipts, deterministic crash injection, and
hash-based reconciliation.

Local validation remains pending on the development workstation.

## v0.9 — Planner / Long-Horizon Execution

Active implementation spans PR #70 through #72.

Core path:

~~~text
Goal
-> PlanProposal
-> DAG validation
-> explicit acceptance
-> append-only plan revisions
-> deterministic step selection
-> v0.8 recovery-aware run per step
-> governed replan when future path changes
~~~

BIO is not part of either axis and remains parked.

## Deferred interoperability

Multi-engine/BIO interoperability remains a later track. The MemoryProvider
seam is preserved so BIO can be resumed without becoming a core dependency.
