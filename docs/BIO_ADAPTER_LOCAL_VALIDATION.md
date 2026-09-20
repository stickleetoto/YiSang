# YiSang BIO Adapter Local Validation

This validates only the YiSang-side BIO adapter boundary. It does not start, modify, or write to a real BIO repository/database.

## Checkout

~~~powershell
git fetch origin
git switch dev/bio-adapter-foundation
git pull
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
~~~

## Focused adapter tests

~~~powershell
python -m pytest `
  tests/test_memory_provider_native.py `
  tests/test_bio_adapter.py `
  tests/test_memory_provider_factory.py `
  tests/test_bio_adapter_smoke.py `
  tests/test_runtime_memory_provider.py `
  tests/test_bio_ab_evaluator.py `
  tests/test_bio_ab_smoke.py `
  tests/test_bio_runtime_smoke.py `
  -q
~~~

Expected:

~~~text
12 passed
~~~

## Adapter smoke

~~~powershell
yisang-bio-adapter-smoke
~~~

Expected important values:

~~~text
ready = true
provider = bio
real_bio_used = false
recall_count = 1
current_memory_id = bio:42
context_memory_count = 1
write_status = pending
proposal_ref = bio-proposal:77
proposal_calls = 1
approval_calls = 0
~~~

The fake bridge deliberately proves that YiSang creates a BIO write proposal but never auto-approves it.

## Full regression

~~~powershell
python -m pytest -q
~~~

Current repository-side CI baseline:

~~~text
320 passed
~~~

## Not proven yet

- Real BIO process/package connectivity
- Real BIO database mutation/review workflow
- YiSangRuntime switching between Native and BIO providers
- Native-vs-BIO Resume/Stale/Correction A/B metrics

Those belong to the next integration/validation slices.


## Runtime provider smoke

~~~powershell
yisang-bio-runtime-smoke
~~~

Expected important values:

~~~text
ready = true
real_bio_used = false
memory_provider_id = bio
memory_context_ref = ctx-runtime-smoke
used_memory_ids = [bio:42]
write_status = pending
proposal_ref = bio-proposal:88
direct_bio_approval = false
~~~

## Synthetic A/B harness smoke

~~~powershell
yisang-bio-ab-smoke
~~~

This runs Resume, Stale, and Correction scenarios against the Native provider
and a fake BIO provider. It validates the evaluator wiring only; it does not
claim BIO superiority or use a live BIO database.
