# v0.9 Planner / Long-Horizon Execution Foundation

> Scope changed by explicit project decision on 2026-09-24.
>
> BIO remains parked. The former roadmap slot "v0.9 Multi-engine / BIO" is
> deferred to a later interoperability track.

## Objective

Represent long-running work as a durable, governed step graph instead of
depending on one model context window.

~~~text
Goal
  -> PlanProposal
  -> structural validation
  -> explicit acceptance
  -> GoalPlan revision 1
  -> deterministic scheduler
  -> step execution
  -> append-only plan revisions
  -> v0.8 recovery per step
~~~

## Plan authority boundary

A planner/model may propose a PlanProposal.

It does not directly mutate durable PlanPort state.

Persistence requires explicit PlanService.accept_proposal(actor, reason, ...).

## Step graph

PlanCompiler validates:

- unique step ids;
- every dependency exists;
- no self dependency;
- no dependency cycles;
- at least one step.

The compiled plan preserves proposal order as a stable ordinal.

## Append-only revisions

Every state transition writes a new GoalPlan revision.

Previous revisions are not overwritten.

~~~text
revision 1  accepted plan
revision 2  step A running
revision 3  step A completed
revision 4  step B running
...
~~~

## Deterministic scheduling

LongHorizonScheduler derives the next action from authoritative plan state.

Selection order for ready steps:

1. higher priority;
2. lower original ordinal;
3. stable step id.

The scheduler does not call an LLM.

## Step lifecycle

~~~text
pending -> running -> completed
             |
             +-> failed -> retry when budget remains

pending/running -> blocked -> pending
~~~

Failed or blocked work can place the plan in blocked state.

A failed step with remaining attempt budget produces retry_step.
Exhausted failures produce replan_required.

## Durability

PlanPort implementations:

- InMemoryPlanPort
- SQLitePlanPort

SQLite stores every revision, not only the latest snapshot.

## Relationship to v0.8

v0.9 chooses and tracks durable steps.

v0.8 remains responsible for:

- run journal;
- policy-controlled actions;
- side-effect receipts;
- checkpoints;
- crash reconciliation.

The next v0.9 slice connects one PlanStep to one durable v0.8 run.


## v0.8 recovery bridge

PlanStep now carries the run_id of its current attempt.

LongHorizonExecutionCoordinator connects durable plan progression to v0.8:

~~~text
scheduler chooses step
  -> Goal becomes/returns active
  -> PlanStep becomes running with run_id
  -> v0.8 RunJournal gets step_planned
  -> recovery-aware runtime performs work
  -> explicit complete_step / fail_step
  -> checkpoint or blocker
  -> next plan decision
~~~

A running step can be recovered after restart because its durable run_id is
passed directly to CrashRecoveryPlanner.

Step completion updates Goal.completed_work / next_action and writes a recovery
checkpoint before advancing.

A failed step blocks the Goal. If attempt budget remains, starting the retry
unblocks the Goal and binds a new run_id.
