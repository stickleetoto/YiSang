# Current State

> Updated: 2026-09-23

YiSang is at the **v0.7 Experience + E.G.O v2 closeout candidate** boundary.

The latest fully released/closed baseline remains **v0.6.0 — Roland Library
validated**. The current open PR stack contains the v0.7 Experience Promotion,
ordered replay, E.G.O v2 lifecycle, adaptive routing, and permission-policy
work that has been implemented and regression-tested but not yet merged to main.

## Stable validated baseline

- v0.4 Governed Memory — validated
- v0.5 Identity Continuity — validated
- v0.6 Roland Library — validated

## v0.7 / E.G.O v2 closeout candidate

Implemented:

- normalized ExperienceEpisode capture
- verified ActionTrace capture
- deterministic single-step replay
- ordered multi-step replay in one isolated workspace
- conservative generalization
- PromotionGate and PromotionArtifact
- explicit approved application boundary
- E.G.O v2 package model
- metadata-first progressive disclosure
- semantic version registry
- SHA-256 package binding
- durable EgoPort
- active / disabled / superseded lifecycle
- PromotionArtifact -> E.G.O package installation
- immutable rollback to prior installed versions
- replay-regression invalidation candidates
- append-only lifecycle audit
- runtime/replay telemetry
- bounded adaptive routing
- principal/action/resource/context policy engine
- deny-by-default policy mode
- explicit permit / forbid with forbid precedence
- resource-scoped execution-time rechecks

## Latest local validation

Windows development environment:

~~~text
yisang-ego-v2-smoke         ready = true
yisang-ego-promotion-smoke  ready = true
yisang-ego-lifecycle-smoke  ready = true
yisang-ego-adaptive-smoke   ready = true
yisang-policy-smoke         ready = true

python -m pytest -q
346 passed in 8.87s
~~~

GitHub Actions also passed the policy branch on Python 3.11 and Python 3.12.

## BIO status: PARKED / RESERVED

BIO integration is intentionally paused.

Reserved branch / PR:

- PR #57 — optional MemoryProvider/BIO adapter
- branch: `dev/bio-adapter-foundation`

Rules while parked:

- do not merge BIO into YiSang core;
- do not make BIO required for runtime startup;
- do not modify the BIO repository from YiSang work;
- preserve the MemoryProvider seam so BIO can be resumed later;
- YiSang must continue to work with native memory only.

See `docs/BIO_RESERVED.md`.

## Current PR graph

~~~text
main
└─ #56  v0.7 Experience Promotion foundation
   ├─ #57  BIO adapter [PARKED / RESERVED]
   ├─ #58  ordered multi-step replay
   └─ #59  E.G.O v2 package foundation
       └─ #60  durable E.G.O lifecycle
           └─ #61  lifecycle guard
               └─ #62  adaptive routing
                   └─ #64  permission policy engine
                       └─ closeout/docs branch
~~~

Old docs-cleanup PR #63 is superseded by the closeout branch because it was
created before the policy-engine work.

## Active next axis

The next major engineering axis is **v0.8 Goal / Recovery Runtime**.

Initial foundation is now under active development on
`dev/v0.8-goal-recovery-foundation`.

Implemented so far on that branch:

- GoalRecord / GoalBudget
- GoalPort with in-memory and SQLite implementations
- explicit goal state transitions
- append-only RunJournalPort
- RecoveryCheckpoint / CheckpointPort
- SQLiteRecoveryStore
- SideEffectReceiptPort
- idempotency request/result digests
- conservative recovery reconciliation
- RecoveryAwareActionRuntime
- goal_id/run_id runtime journal context
- duplicate side-effect suppression from committed receipts

The v0.8 branch has not been declared validated yet; local testing is delegated
to the development workstation.

Target:

Target:

~~~text
durable Goal
  -> run journal
  -> checkpoint
  -> interruption / restart
  -> restore
  -> determine completed side effects
  -> resume from next safe action
~~~

Policy expansion to real side-effect capabilities remains a supporting track,
not a separate major axis.

See `docs/NEXT_AXIS.md`.
