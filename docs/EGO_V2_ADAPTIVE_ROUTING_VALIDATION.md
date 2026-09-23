# E.G.O v2 Adaptive Routing Local Validation

This validates outcome telemetry and bounded adaptive routing on top of the
durable E.G.O lifecycle guard.

## Checkout

~~~powershell
git fetch origin
git switch dev/ego-v2-adaptive-routing
git pull
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
~~~

## Focused tests

~~~powershell
python -m pytest `
  tests/test_ego_telemetry.py `
  tests/test_ego_adaptive_router.py `
  tests/test_runtime_ego_telemetry.py `
  tests/test_ego_lifecycle_telemetry.py `
  tests/test_ego_adaptive_smoke.py `
  -q
~~~

## Adaptive routing smoke

~~~powershell
yisang-ego-adaptive-smoke
~~~

Expected important values:

~~~text
ready = true
min_samples = 3
replay_health_weighted = true
bounded_adjustment = true
selected_order begins with ego.stable
~~~

## Invariants

- Fewer than 3 telemetry samples produce zero adaptive adjustment.
- Adaptive feedback is version-scoped.
- Replay health has more weight than ordinary runtime outcome by default.
- Old telemetry decays with a configurable half-life.
- Signed routing adjustment is capped at +/-0.35 by default.
- Telemetry cannot make a semantically irrelevant E.G.O route by itself.
- Telemetry cannot install, disable, rollback, or grant permissions.
- Replay failure invalidation remains governed by the separate lifecycle guard.

## Full regression

~~~powershell
python -m pytest -q
~~~

Repository-side CI baseline: 336 passed on Python 3.11/3.12.
