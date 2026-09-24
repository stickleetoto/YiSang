# Current State

> Updated: 2026-09-24

YiSang is currently developing the **v0.9 Planner / Long-Horizon Execution**
axis on top of the v0.8 Goal / Recovery Runtime.

## Stable validated baseline

- v0.4 Governed Memory — validated
- v0.5 Identity Continuity — validated
- v0.6 Roland Library — validated
- v0.7 / E.G.O v2 / Policy — implemented and locally validated before closeout

Latest closed local regression evidence before v0.8 work:

~~~text
E.G.O v2 / promotion / lifecycle / adaptive / policy smokes: PASS
python -m pytest -q
346 passed in 8.87s
~~~

## BIO

BIO is **PARKED / RESERVED**.

- PR #57 remains available.
- Native memory remains the default.
- v0.8 and v0.9 do not depend on BIO.
- BIO work resumes only for a concrete future validation goal.

## v0.8 Goal / Recovery Runtime

Development stack:

- #66 Goal and recovery foundation
- #67 Restart assessment and recovery controller
- #68 Crash recovery orchestration
- #69 Real workspace side-effect recovery

Implemented:

- durable GoalRecord / GoalPort
- SQLite goal persistence
- append-only RunJournal
- recovery checkpoints
- SideEffectReceipt
- idempotency keys
- RecoveryAwareActionRuntime
- crash directives
- explicit uncertain-side-effect reconciliation
- retry authorization
- verified checkpoint orchestration
- real workspace.write_text side effect
- atomic workspace writes
- SHA-256 preconditions
- deterministic crash injection
- exact-hash uncertain-write reconciliation
- duplicate side-effect suppression after committed receipt

Local validation for v0.8 is pending on the development workstation.

## v0.9 Planner / Long-Horizon Execution

The former v0.9 Multi-engine/BIO slot was explicitly reassigned to long-horizon
planning. Multi-engine/BIO moved to a deferred interoperability track.

Development stack:

- #70 Durable planner foundation
- #71 PlanStep / v0.8 recovery bridge
- #72 Governed replanning

Implemented:

- PlanProposal / PlanStepSpec
- DAG validation and cycle rejection
- explicit plan acceptance boundary
- append-only GoalPlan revisions
- InMemory and SQLite PlanPort
- deterministic LongHorizonScheduler
- per-step retry budgets
- PlanStep -> durable v0.8 run_id binding
- long-horizon Goal/Recovery bridge
- step completion checkpoints
- crash recovery for running steps
- governed PlanRevisionProposal
- stale revision rejection
- completed-step immutability
- existing step-id semantic immutability
- future failed/pending path replacement through new step ids

Local validation for v0.9 is pending on the development workstation.

## Active PR graph

~~~text
main
└─ #56 v0.7 Experience foundation
   ├─ #57 BIO adapter [PARKED]
   ├─ #58 ordered replay
   └─ #59 E.G.O v2 foundation
       └─ #60 durable E.G.O
           └─ #61 lifecycle guard
               └─ #62 adaptive routing
                   └─ #64 permission policy
                       └─ #65 v0.7/E.G.O closeout
                           └─ #66 v0.8 goal/recovery
                               └─ #67 restart controller
                                   └─ #68 crash orchestration
                                       └─ #69 real side effects
                                           └─ #70 v0.9 planner
                                               └─ #71 plan/recovery bridge
                                                   └─ #72 governed replan
~~~

## Current development rule

Do not add BIO dependency.

Do not let planner/model output mutate PlanPort directly.

Do not automatically repeat uncertain side effects.

Do not erase completed plan evidence during replanning.

Local smoke/pytest execution is delegated to the development workstation.
