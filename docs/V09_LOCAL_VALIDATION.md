# v0.9 Local Validation

> Environment: Windows development workstation
> Date: 2026-09-24
> Branch: `dev/v0.9-governed-replanning`

## Smoke results

### workspace recovery

~~~json
{
  "ready": true,
  "crash_seen": true,
  "directive_before_reconcile": "reconcile_side_effect",
  "inspection_status": "matches_expected",
  "receipt_state_after_reconcile": "committed",
  "duplicate_execution_skipped": true,
  "duplicate_receipt_id_same": true
}
~~~

### planner

~~~json
{
  "ready": true,
  "accepted_revision": 1,
  "step_order": ["inspect", "edit", "verify"],
  "final_state": "completed",
  "final_revision": 7,
  "history_length": 7
}
~~~

### long-horizon

~~~json
{
  "ready": true,
  "first_step": "inspect",
  "running_resume_decision": "recover_running_step",
  "running_resume_run_id": "run-inspect",
  "second_step": "edit",
  "final_plan_state": "completed",
  "final_goal_state": "completed",
  "plan_revision": 5
}
~~~

### governed replan

~~~json
{
  "ready": true,
  "decision_before_replan": "replan_required",
  "completed_step_preserved": true,
  "replacement_step": "alternative",
  "final_plan_state": "completed",
  "final_goal_state": "completed",
  "replan_history_count": 1
}
~~~

## Focused regression

Command:

~~~powershell
python -m pytest -q `
  tests/test_workspace_write_recovery.py `
  tests/test_recovery_fault_injection.py `
  tests/test_workspace_write_reconcile.py `
  tests/test_workspace_recovery_smoke.py `
  tests/test_planning_foundation.py `
  tests/test_plan_recovery_bridge.py `
  tests/test_governed_replanning.py
~~~

Result:

~~~text
23 passed in 0.41s
~~~

## Validation status

Validated locally:

- real workspace side-effect recovery
- deterministic crash/reconcile path
- duplicate side-effect suppression
- durable planner foundation
- long-horizon PlanStep -> recovery-run bridge
- running-step recovery routing
- governed replanning
- preservation of completed step evidence

Pending before declaring the complete v0.8/v0.9 stack regression-clean:

~~~powershell
python -m pytest -q
~~~
