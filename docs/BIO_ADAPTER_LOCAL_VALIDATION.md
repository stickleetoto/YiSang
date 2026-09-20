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
313 passed
~~~

## Not proven yet

- Real BIO process/package connectivity
- Real BIO database mutation/review workflow
- YiSangRuntime switching between Native and BIO providers
- Native-vs-BIO Resume/Stale/Correction A/B metrics

Those belong to the next integration/validation slices.
