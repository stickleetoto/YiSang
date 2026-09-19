# YiSang v0.4 Memory Benchmark

The v0.4 memory benchmark is a deterministic harness for validating retrieval,
governance, quarantine, and poisoning resistance before adding larger external
benchmarks.

## Built-in categories

The baseline contains 40 cases: 10 cases in each of four categories:

- `static_dynamic`
- `workflow_gotcha`
- `cross_session`
- `poisoning`

The default profile seeds governed `MemoryProposal` objects, routes them through
`MemoryWritePipeline`, performs retrieval through a rebuildable projected
MemoryPort, and records whether expected memories were retrieved and forbidden
memories escaped quarantine.

The harness also exposes five comparison profiles matching the roadmap:

- `memory_disabled`
- `session_only`
- `retrieval_memory`
- `retrieval_procedural`
- `retrieval_procedural_provenance`

The first two deliberately have no durable retrieval; the ungoverned retrieval
profiles show what happens when provenance/quarantine policy is bypassed.

## Run

~~~powershell
yisang-eval-memory --output ".\artifacts\memory-v04.json"

yisang-eval-memory `
  --profile retrieval_memory `
  --output ".\artifacts\memory-v04-ungoverned.json"
~~~

Selected cases:

~~~powershell
yisang-eval-memory `
  --case poison-ignore-policy `
  --case cross-session-engine-swap `
  --output ".\artifacts\memory-focused.json"
~~~

## Metrics

The report records per-case:

- pass/fail
- retrieved contents
- expected recall
- precision
- forbidden hits
- committed / quarantined / rejected seed counts
- retrieval latency

The summary records:

- overall pass rate
- mean recall
- forbidden-hit count
- poisoning escape rate
- category-level pass rate / recall

## Scope

This is a local deterministic benchmark, not a replacement for LongMemEval-V2,
EvoMemBench, or model-in-the-loop evaluation.

Its role is to catch architectural regressions cheaply and repeatedly before
running more expensive external or model-backed evaluations.
