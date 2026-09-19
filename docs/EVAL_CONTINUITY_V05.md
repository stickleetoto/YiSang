# YiSang v0.5 Live Continuity Evaluation

This runner is the bridge from deterministic unit fixtures to the real v0.5
exit criterion: attach one reasoning engine, snapshot YiSang, replace the engine,
restore the same persistent agent state, and prove the replacement engine sees
the same identity/memory/capabilities.

## What the runner does

For every repeat:

1. create a source YiSang runtime with a seeded durable memory, E.G.O capability,
   active project, goal, and tags
2. issue a source-engine probe and verify the expected memory/E.G.O were selected
3. build a portable continuity bundle
4. create a fresh target runtime
5. restore the bundle onto the target engine
6. compare identity, goal, state, memory digest, E.G.O digest, and continuity
   fingerprint before continuing
7. issue a target-engine probe
8. verify the target engine was actually used and the same durable memory/E.G.O
   remain reachable
9. record restore and probe latency

Model wording is intentionally not required to match. Persistent state is.

## Example

~~~powershell
yisang-eval-continuity `
  --source-base-url http://127.0.0.1:11434/v1 `
  --source-model "<source-model>" `
  --source-engine-id source `
  --target-base-url http://127.0.0.1:11434/v1 `
  --target-model "<target-model>" `
  --target-engine-id target `
  --repeats 5 `
  --output ".\artifacts\continuity-v05.json"
~~~

The source and target may share one OpenAI-compatible server as long as they are
different model selections. They may also point to different compatible servers.

## Report

The JSON report includes:

- per-run pass/fail
- source and target engine participation
- identity / goal / state preservation
- authoritative memory preservation
- E.G.O capability preservation
- continuity fingerprint preservation
- expected memory retrieval on both engines
- expected E.G.O selection on both engines
- restore latency
- combined source/target probe latency
- source and target responses for inspection
- mean and p95 latency summaries

## Exit-criterion rule

Passing deterministic EchoEngine tests proves the harness logic, not the v0.5
product claim. v0.5 still requires successful runs across at least two genuinely
different reasoning-engine families.
