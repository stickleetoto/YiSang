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
python -m pytest tests/test_experience_promotion_v07.py tests/test_experience_application_v07.py tests/test_experience_recorder_v07.py tests/test_experience_store_v07.py tests/test_runtime_experience_v07.py tests/test_experience_smoke_v07.py tests/test_experience_generalizer_v07.py tests/test_experience_replay_plan_v07.py tests/test_experience_generalization_smoke_v07.py tests/test_experience_executor_v07.py tests/test_experience_real_replay_smoke_v07.py tests/test_experience_trace_v07.py tests/test_experience_trace_store_compiler_v07.py tests/test_runtime_trace_v07.py tests/test_experience_trace_replay_smoke_v07.py tests/test_experience_multistep_v07.py tests/test_experience_ordered_replay_smoke_v07.py -q
~~~

## 4. Full regression

~~~powershell
python -m pytest -q
~~~

Expected repository-side CI baseline at the time this document was written:

~~~text
307 passed
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


## 8. Repeated-experience generalization smoke

This smoke uses three synthetic but independently verified source episodes. It tests the deterministic middle path without an external LLM or real tool side effects.

~~~powershell
yisang-generalization-smoke
~~~

Expected important values:

~~~text
ready = true
source_episode_count = 3
success_count = 3
replay_case_count = 3
simulated_replay_results = true
promotion_accepted = true
~~~

The simulated replay flag is intentional. This validates Episode -> Generalizer -> LessonCandidate -> ReplayPlan -> ReplayReport -> PromotionGate wiring; it does not claim real tools were replayed.


## 9. Deterministic subprocess replay smoke

This smoke performs three real subprocess executions in isolated temporary
workspaces. It does not use a shell and only allows the current Python
interpreter.

~~~powershell
yisang-real-replay-smoke
~~~

Expected important values:

~~~text
ready = true
replay_case_count = 3
executed_subprocess_replays = 3
all_replays_passed = true
evidence_refs_present = true
shell_used = false
promotion_accepted = true
~~~

Each replay writes a file, checks exact file content and stdout, records an
observation digest as replay evidence, and then feeds the real ReplayReport into
PromotionGate.


## 10. Runtime trace -> replay manifest smoke

This smoke records three verified action traces, persists only hashes for raw
tool arguments, compiles trusted replay manifests, executes them, and feeds the
real replay report into PromotionGate.

~~~powershell
yisang-trace-replay-smoke
~~~

Expected important values:

~~~text
ready = true
recorded_trace_count = 3
compiled_manifest_count = 3
executed_replay_count = 3
all_replays_passed = true
raw_action_arguments_stored = false
promotion_accepted = true
~~~

Replay manifests are opt-in tool evidence. YiSang does not reconstruct shell
commands from arbitrary model text or raw action arguments.


## 11. Ordered multi-step replay smoke

This smoke proves two replayable tool steps execute in order inside the same
isolated workspace. The second step depends on a file created by the first.

~~~powershell
yisang-ordered-replay-smoke
~~~

Expected important values:

~~~text
ready = true
sequence_count = 3
steps_per_sequence = [2, 2, 2]
shared_workspace_proven = true
fail_fast = true
all_replays_passed = true
promotion_accepted = true
~~~

The ordered compiler requires the complete ActionTrace tool sequence to match
the generalized procedure tool order exactly. Missing, extra, reordered, or
unverified steps are rejected instead of guessed.
