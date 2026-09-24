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

## Runtime goal/run integration

YiSangRequest metadata may now carry:

~~~text
goal_id
run_id
~~~

When a RunJournalPort is configured, YiSangRuntime records goal-start and
verification events and returns the durable journal cursor in YiSangResponse.

RecoveryAwareActionRuntime adds action-level evidence:

~~~text
action_proposed
-> action_authorized
-> [side_effect_reserved]
-> action_executed
-> [side_effect_committed | side_effect_failed]
~~~

For side-effecting tools, recovery-aware execution requires:

- goal_id + run_id execution context;
- a stable ActionProposal.idempotency_key.

If an identical committed receipt already exists, the handler is not invoked
again and the action is returned as a recovered skip.

If only a started receipt exists, execution is denied as uncertain. YiSang does
not guess whether the external side effect happened before the crash.

## Deliberate non-goals

This slice still does not:

- automatically transition GoalRecord based on runtime output;
- automatically retry failed side effects;
- infer uncertain external state;
- autonomously create or replan goals;
- depend on BIO.

## Next slice

Recommended:

~~~text
crash-point state machine
+ explicit retry/reconcile decisions
+ GoalRecord/runtime progress integration
+ checkpoint-after-verification controller
+ restart/resume orchestration
~~~


## Restart assessment

RecoveryCoordinator.assess_restart() combines:

- current GoalRecord state;
- latest checkpoint;
- journal events after the checkpoint;
- all durable side-effect receipts for the goal.

Automatic resume is blocked when any receipt is still in started state because
the external mutation may have happened before the crash even though commit was
not recorded.

~~~text
started receipt
  -> uncertain_side_effects
  -> resume_allowed = false
  -> explicit reconciliation required
~~~

A failed receipt is retryable only after an explicit authorize_retry() call.
Retry reopens the same logical receipt, increments attempt_count, records the
new run_id, and appends a recovery_decision journal event.

Uncertain started receipts can be explicitly resolved as committed or failed
after external inspection.

## Recovery run controller

RecoveryRunController provides explicit lifecycle operations:

- start
- checkpoint
- block
- unblock
- complete
- cancel
- assess_restart

These operations update GoalRecord through GoalService and emit durable journal
evidence. The controller does not autonomously choose a new plan.


## Crash-point recovery directive

CrashRecoveryPlanner reduces restart state to one of five safe directives:

~~~text
resume_next_action
reconcile_side_effect
verify_prior_action
write_checkpoint
stop
~~~

Examples:

- unresolved started receipt -> reconcile_side_effect;
- action/side effect executed but no verification -> verify_prior_action;
- PASS verification after latest checkpoint -> write_checkpoint;
- current checkpoint with no newer events -> resume_next_action;
- completed/cancelled/blocked goal -> stop.

The planner returns a directive only. It does not execute recovery automatically.

## Verified checkpoint orchestration

VerifiedCheckpointOrchestrator can be attached to YiSangRuntime.

It writes a checkpoint only when:

- goal_id + run_id are present;
- verification status is PASS;
- every action result is EXECUTED.

Checkpoint creation is idempotent per goal + run + request_id.

The checkpoint records committed side-effect receipt ids as completed action
references. YiSangResponse exposes recovery_checkpoint_id when a checkpoint is
created or reused.


## Real workspace side-effect integration

The v0.8 real-side-effect slice adds workspace.write_text.

Properties:

- workspace-relative path enforcement;
- UTF-8 size limit;
- atomic temp-file + os.replace write;
- optional expected SHA-256 precondition;
- optional must-not-exist precondition;
- optional parent creation inside the workspace only;
- filesystem.write policy action;
- repository_edit E.G.O capability requirement;
- filesystem=workspace permission requirement;
- side-effect receipt + idempotency key integration.

Recovery metadata stores only the workspace-relative path and expected content
hash/size, not the raw file content.

## Deterministic crash injection

RecoveryAwareActionRuntime accepts an optional fault injector for development
and local validation.

Supported fault points:

~~~text
after_side_effect_reserved
after_handler_success_before_receipt_commit
after_side_effect_committed
~~~

Injected crashes inherit directly from BaseException so normal tool exception
handling does not incorrectly convert a simulated process death into an
ordinary failed tool call.

## Workspace uncertain-write reconciliation

WorkspaceWriteReconciler can inspect a started workspace.write_text receipt.

If the actual file SHA-256 exactly matches the expected hash stored in receipt
metadata, the uncertain receipt can be explicitly resolved as committed with
filesystem evidence.

Missing or mismatched files are not auto-classified as failed because the file
may have changed again after the original side effect.
