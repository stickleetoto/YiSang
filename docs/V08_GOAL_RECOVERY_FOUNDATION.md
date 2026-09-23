# v0.8 Goal / Recovery Foundation

> Initial implementation slice

## Scope

This foundation makes ongoing work durable before autonomous planning is added.

Implemented contracts:

~~~text
GoalRecord
  -> GoalPort
       +-- InMemoryGoalPort
       +-- SQLiteGoalPort

RunJournalEvent
  -> RunJournalPort
       +-- InMemoryRunJournalPort
       +-- SQLiteRecoveryStore

RecoveryCheckpoint
  -> CheckpointPort
       +-- InMemoryCheckpointPort
       +-- SQLiteRecoveryStore

RecoveryCoordinator
  -> write_checkpoint()
  -> plan_resume()
~~~

## Goal state machine

~~~text
planned -> active -> completed
            |
            +-> blocked -> active
            |
            +-> cancelled

planned -> cancelled
blocked -> cancelled
~~~

Completed and cancelled goals are terminal.

Goal progress fields include:

- milestones
- completed_work
- blockers
- next_action
- exit_condition
- attempt/failure/token/time budgets
- provenance

## Run journal

The journal is append-only evidence, not memory.

Initial event vocabulary:

- goal_started
- step_planned
- action_proposed
- action_authorized
- action_executed
- verification_result
- checkpoint_written
- blocker_detected
- goal_completed
- goal_cancelled

Sequence numbers are monotonic per goal + run.

## Checkpoint semantics

A checkpoint captures:

- goal id
- run id
- covered journal sequence
- goal state
- next action
- completed action references
- blockers
- metadata

Writing a checkpoint also appends a checkpoint_written journal event.

## Conservative resume planning

RecoveryCoordinator.plan_resume() currently returns:

- completed -> no resume
- cancelled -> no resume
- blocked -> no resume until blocker handling
- planned/active -> resume allowed

When a checkpoint exists, its recovery cursor and completed action references
are preferred over reconstructing from free-form model state.

## Side-effect receipts and idempotency

The foundation now includes a durable SideEffectReceiptPort.

Receipt states:

~~~text
started
  -> committed
  -> failed
~~~

Recovery interpretation:

~~~text
no receipt
  -> execute

committed
  -> skip; already completed

started
  -> review; the process may have crashed after the external effect but
     before commit was recorded

failed
  -> retry may be allowed
~~~

An idempotency key is unique per goal. Reusing the same key with a different
tool/request digest is treated as a conflict rather than guessed.

A canonical SHA-256 helper is provided for tool id + arguments.

## Deliberate non-goals

This slice still does not:

- connect GoalPort directly to YiSangRuntime;
- automatically execute a recovered action;
- autonomously create or replan goals;
- infer whether an uncertain started receipt actually mutated the world;
- depend on BIO.

## Next slice

Recommended:

~~~text
Runtime goal/run integration
+ automatic journal events around ActionRuntime
+ receipt reservation/commit around side-effecting tools
+ crash-point state machine
+ deterministic resume controller
~~~
