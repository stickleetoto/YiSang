# YiSang Gym v0.1

YiSang Gym is a low-risk development practice harness for building verified
agent experience before assigning important repositories.

The first version deliberately does not auto-promote Gym runs into durable
YiSang Experience, Roland knowledge, E.G.O packages, or model training data.
A successful run is evidence for later review, not automatic learning.

## Safety model

Each task is copied into an isolated run directory:

~~~text
.gym/runs/<run-id>/
  manifest.json
  result.json
  workspace/
    GYM_TASK.md
    ...task seed...
~~~

The manifest stays outside the agent workspace and contains a content-hash
baseline plus the task allowlist. The checker reports modifications, creations,
and deletions outside the allowlist. It also rejects symlinks before executing
verification commands.

Verification commands come from the trusted task manifest copied at prepare
time and are executed as argv lists, never through a shell.

This is a development containment harness, not an OS security sandbox. Rules
such as no network access still depend on the outer Codex sandbox or operator
configuration. Do not run untrusted task specifications.

## Basic workflow

List tasks:

~~~powershell
yisang-gym list
~~~

Prepare the first task:

~~~powershell
yisang-gym prepare --task 001-log-inspector
~~~

The command prints a run directory and workspace. Start Codex in the returned
workspace and assign the task described by GYM_TASK.md.

When Codex stops:

~~~powershell
yisang-gym check --run ".\.gym\runs\<run-id>"
~~~

A run is ready only when both are true:

- the scope check passes;
- every trusted verification command exits with code 0.

The checker writes result.json so later episode tooling can ingest the outcome.

## v0.1 task policy

The first task allows one file to change: log_inspector.py. Tests and
GYM_TASK.md are outside the allowlist. This makes the task useful for measuring
whether the agent can inspect requirements, implement a small feature, run
tests, and stop without unnecessary edits.

## Promotion policy

For now, one PASS is not durable skill acquisition.

Recommended gate before a pattern becomes governed Experience:

1. result.json reports ready=true;
2. no scope or policy violations occurred;
3. verification passes from a clean prepared run;
4. the same class of task succeeds in at least three independent runs;
5. replay evidence confirms the trajectory;
6. a human or governed promotion policy approves it.

This keeps Gym useful for experience generation without turning model mistakes
into persistent agent behavior.
