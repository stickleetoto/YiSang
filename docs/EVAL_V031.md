# YiSang v0.3.1 Repeatability Evaluation

This document defines the repeatability gate for the v0.3.1 harness-stabilization milestone.

## Goal

A single successful Codex run is not enough. The same bounded task should succeed repeatedly without malformed tool calls, runaway retries, or duplicated side effects.

The built-in matrix is exposed by `yisang.eval.codex_matrix.DEFAULT_CODEX_V031_MATRIX`.

Current cases:

- `read-file`
- `write-exact-file`
- `edit-one-line`
- `create-directory`
- `git-status`
- `missing-file-recovery`
- `stop-after-success`

## Run the real Codex matrix

Install the checkout first:

~~~powershell
python -m pip install -e ".[dev]"
~~~

Then run, for example:

~~~powershell
$env:CODEX_HOME = "$env:USERPROFILE\.codex-yisang-test"

yisang-eval-codex `
  --repetitions 5 `
  --codex-home "$env:CODEX_HOME" `
  --workspace-root "$env:TEMP\yisang-eval-workspaces" `
  --output ".\artifacts\v031-runs.jsonl"
~~~

The runner creates isolated temporary workspaces, initializes git when available, invokes `codex exec` through stdin, verifies case artifacts, and records one JSON object per run.

You can run only selected cases:

~~~powershell
yisang-eval-codex `
  --repetitions 10 `
  --codex-home "$env:CODEX_HOME" `
  --case write-exact-file `
  --case stop-after-success `
  --output ".\artifacts\focused-runs.jsonl"
~~~

## Aggregate and gate the results

~~~powershell
yisang-eval-repeatability `
  --input ".\artifacts\v031-runs.jsonl" `
  --output ".\artifacts\v031-report.json" `
  --min-success-rate 0.90
~~~

The command exits non-zero if any case is below the requested success rate or if duplicate side effects were recorded.

## Metrics

Each run may record:

~~~text
success
tool_calls
malformed_tool_calls
retries
completion_after_success
latency_ms
context_tokens
duplicate_side_effects
error
~~~

The report aggregates:

~~~text
success_rate
mean tool calls
malformed tool-call rate
mean retries
completion-after-success rate
p50 latency
p95 latency
mean context tokens
duplicate side effects
~~~

## v0.3.1 baseline gate

The roadmap target is:

- each case success rate >= 90%
- no duplicate side effects
- unknown textual tool calls are never promoted
- malformed known calls are normalized safely or rejected
- successful bounded tasks do not continue into unrelated tool activity

The real local baseline is intentionally not committed as a claim until the matrix has been run against the target Codex/YiSang/local-model stack.
