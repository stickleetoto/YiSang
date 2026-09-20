# YiSang v0.7 Local Validation

This checklist validates the current Experience Promotion development branch on
Windows without requiring an external LLM.

## 1. Checkout the branch

~~~powershell
git fetch origin
git checkout dev/v0.7-experience-foundation
git pull
~~~

## 2. Activate the existing virtual environment

~~~powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
~~~

## 3. Focused v0.7 tests

~~~powershell
python -m pytest tests/test_experience_promotion_v07.py tests/test_experience_application_v07.py tests/test_experience_recorder_v07.py tests/test_experience_store_v07.py tests/test_runtime_experience_v07.py tests/test_experience_smoke_v07.py -q
~~~

## 4. Full regression

~~~powershell
python -m pytest -q
~~~

Expected repository-side CI baseline at the time this document was written:

~~~text
267 passed
~~~

## 5. Runtime persistence smoke

~~~powershell
yisang-experience-smoke --db ".\artifacts\experience-v07-smoke.db"
~~~

Expected shape:

~~~json
{
  "ready": true,
  "verification_status": "PASS",
  "episode_count_after_reopen": 1,
  "outcome": "success",
  "raw_request_stored": false
}
~~~

The exact generated episode id is intentionally variable.

## 6. Inspect captured episodes

~~~powershell
yisang-experience-audit --db ".\artifacts\experience-v07-smoke.db" --json
~~~

Expected important values:

~~~text
episode_count = 1
success_count = 1
failure_count = 0
~~~

The smoke uses an EchoEngine and does not require LM Studio, Ollama, or Codex.
It proves the core runtime -> ExperienceRecorder -> SQLiteExperiencePort ->
restart/read path.

## 7. What this does not prove yet

This local smoke does not yet prove automatic learning from a real Codex tool
session. Codex executes tools outside the YiSang model proxy, so client-side
tool evidence must be correlated explicitly before it can become trusted
promotion evidence.

That integration is a later v0.7 slice. Do not infer tool success from model
text alone.
