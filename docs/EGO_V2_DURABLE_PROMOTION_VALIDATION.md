# Durable E.G.O Promotion Local Validation

This validates the E.G.O v2 durable installation lifecycle built on top of the
E.G.O v2 foundation.

## Checkout

~~~powershell
git fetch origin
git switch dev/ego-v2-durable-port
git pull
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
~~~

## Focused tests

~~~powershell
python -m pytest `
  tests/test_ego_v2_package.py `
  tests/test_ego_v2_registry.py `
  tests/test_ego_v2_router.py `
  tests/test_ego_v2_continuity.py `
  tests/test_ego_v2_progressive_continuity.py `
  tests/test_ego_durable_port.py `
  tests/test_ego_promotion_apply.py `
  tests/test_ego_promotion_smoke.py `
  -q
~~~

## Promotion-to-E.G.O smoke

~~~powershell
yisang-ego-promotion-smoke
~~~

Expected important values:

~~~text
ready = true
installed_versions = [0.0.1, 0.0.2]
active_after_second_apply = 0.0.2
routed_version = 0.0.2
runtime_selected_ego_ids = [ego.learned.python-debug]
runtime_context_used_promoted_ego = true
rollback_target = 0.0.1
active_after_rollback = 0.0.1
promotion_receipts = 2
package_digest_bound = true
~~~

This smoke proves the full controlled path:

~~~text
validated PromotionArtifact
  -> explicit approved apply
  -> durable E.G.O v2 package
  -> active-version supersession
  -> registry view
  -> hybrid routing
  -> YiSangRuntime context use
  -> rollback
~~~

It does not grant new tool permissions. Generated promoted E.G.O packages use
prompt runtime only and retain conservative risk hints.

## Full regression

~~~powershell
python -m pytest -q
~~~

Repository-side CI baseline before lifecycle guard: 320 passed on Python 3.11/3.12.


## Post-install lifecycle guard

A later replay failure does not automatically remove or disable an installed
E.G.O. It creates a pending invalidation candidate.

~~~text
active E.G.O
  -> later replay failure
  -> pending invalidation candidate
  -> review
       +-- reject -> keep active
       +-- approve -> disable
  -> optional rollback to an earlier installed version
~~~

All install, supersede, disable, rollback, candidate-create, approve, and reject
operations are recorded as append-only audit events.

~~~powershell
yisang-ego-lifecycle-smoke
~~~

Expected important values:

~~~text
ready = true
pending_candidate_does_not_disable = true
rejected_candidate_keeps_active = true
approved_candidate_disables = true
rollback_version = 0.0.1
~~~
