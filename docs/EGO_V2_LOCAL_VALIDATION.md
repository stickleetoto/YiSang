# E.G.O v2 Local Validation

This validates the E.G.O v2 capability-package foundation without enabling any
WASM, remote execution, OCI registry, signature, or external policy engine.

## Checkout

~~~powershell
git fetch origin
git switch dev/ego-v2-foundation
git pull
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
~~~

## Focused tests

~~~powershell
python -m pytest `
  tests/test_ego_loader.py `
  tests/test_ego_router.py `
  tests/test_ego_v2_package.py `
  tests/test_ego_v2_registry.py `
  tests/test_ego_v2_router.py `
  tests/test_ego_v2_continuity.py `
  tests/test_ego_v2_progressive_continuity.py `
  tests/test_ego_v2_smoke.py `
  -q
~~~

## Smoke

~~~powershell
yisang-ego-v2-smoke
~~~

Expected important values:

~~~text
ready = true
discovered_versions = [1.0.0, 1.2.0]
selected_version = 1.2.0
metadata_only_before_activation = true
package_digest_bound_before_activation = true
full_loaded_after_activation = true
digest_stable_across_activation = true
a2a_skill_id = ego.python.debug
~~~

## Full regression

~~~powershell
python -m pytest -q
~~~

Repository-side CI baseline is updated after the branch CI completes.
