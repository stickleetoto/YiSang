# E.G.O v2 Permission Policy Local Validation

This validates the first explicit E.G.O authorization-policy boundary.

The policy engine is optional. When it is not configured, the legacy
capability/permission behavior remains unchanged.

## Checkout

~~~powershell
git fetch origin
git switch dev/ego-v2-policy-engine
git pull
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
~~~

## Policy smoke

~~~powershell
yisang-policy-smoke
~~~

Expected important values:

~~~text
ready = true
tool_exposed_for_partial_scope = true
allowed_resource_status = EXECUTED
explicit_forbid_status = DENIED
explicit_forbid_reason = policy_denied
unmatched_resource_status = DENIED
unmatched_resource_reason = policy_no_permit
deny_by_default = true
risk_hints_grant_authority = false
~~~

## Focused tests

~~~powershell
python -m pytest `
  tests/test_policy_engine.py `
  tests/test_action_gate.py `
  tests/test_action_gate_policy.py `
  tests/test_action_runtime.py `
  tests/test_policy_smoke.py `
  -q
~~~

## Full regression

~~~powershell
python -m pytest -q
~~~

Repository-side CI baseline: 346 passed on Python 3.11/3.12.

## Invariants

- A model proposal never creates execution authority.
- Legacy E.G.O capability and permission checks run before policy evaluation.
- A configured policy engine is deny-by-default.
- An explicit forbid overrides matching permits.
- Tool exposure is only a preflight; actual resource arguments are checked
  again during execution.
- Resource-scoped forbids do not hide a tool when other resources are allowed.
- E.G.O risk hints are advisory context only and never grant authority.
- The policy engine does not install, enable, disable, or mutate E.G.O packages.
- No Cedar/OPA runtime dependency is required by this foundation.


## Windows local validation

Validated on the user's Windows development environment on 2026-09-23:

~~~text
yisang-policy-smoke
ready = true

python -m pytest -q
346 passed in 8.87s
~~~

This confirms the policy smoke and the full repository regression suite pass
outside GitHub Actions as well as in Python 3.11/3.12 CI.
