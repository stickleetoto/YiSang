# YiSang Guarded Execution

## Purpose

YiSang treats tool execution as a separate authority boundary from model
reasoning.

A model may propose a tool call, but proposal does not imply permission.

```text
LLM / Agent Backend
      |
      v
ActionProposal
      |
      v
ActionGate
      |
      +-- unknown tool? ----------------> DENIED
      +-- missing E.G.O capability? ----> DENIED
      +-- insufficient permission? -----> DENIED
      +-- side effects disabled? --------> DENIED
      |
      v
ActionRuntime
      |
      +-- argument validation failure --> ERROR
      +-- handler error -----------------> ERROR
      |
      v
ActionResult(EXECUTED)
      |
      v
bounded feedback to compatible engine
```

## Tool surface

Only tools already authorized by the selected E.G.O set are exposed to the
reasoning engine. `ActionRuntime.available_tools()` asks the same `ActionGate`
used at execution time, so an unavailable tool is not merely hidden by prompt
convention: it is also denied if the model invents its id.

Each tool declares:

- stable `tool_id`
- callable handler
- human-readable description
- required E.G.O capabilities
- required permissions
- argument schema
- whether it has side effects

Every tool must require at least one E.G.O capability.

## Structured action protocol

OpenAI-compatible engines can decode both:

1. a provider-neutral JSON envelope:

```json
{
  "response": "I need one more piece of evidence.",
  "actions": [
    {
      "tool": "workspace.read_text",
      "arguments": {"path": "README.md"}
    }
  ]
}
```

2. OpenAI-style `message.tool_calls` when an endpoint returns them.

Malformed action entries fail closed at decoding time. Action count and
serialized argument size are bounded.

## Tool feedback loop

Engines opt into repeated action feedback via `supports_action_feedback`.
Legacy engines do not opt in and retain one-shot behavior.

Compatible engines may:

```text
reason
 -> request authorized action
 -> receive deterministic ActionResult
 -> reason again
 -> request another action or answer
```

The loop is bounded by `YiSangRuntime.max_action_rounds`. If the engine still
requests an action after the limit, YiSang records a structured denial with
`gate_reason=action_loop_limit`.

## Tool output trust

Tool output is injected back into context as **untrusted data/evidence**.
It does not redefine identity, policy, permissions, or instructions.

The context compiler bounds action-result history so large tool payloads cannot
grow context without limit. Non-JSON Python values are converted to safe string
representations before context serialization.

## Read-only workspace tools

`register_workspace_read_tools()` provides:

- `workspace.list`
- `workspace.read_text`

Both require the `repository_analysis` capability and `filesystem: read`
permission. Paths are resolved under a configured workspace root. `..`,
absolute-path escape, and symlink escape resolve outside the root and are
rejected.

These tools are intentionally read-only. File mutation and shell execution
remain future side-effecting capabilities requiring stronger approval policy.

## Argument validation

`ToolDefinition.argument_schema` supports a lightweight object-schema contract:

- `required`
- property `type`
- `additionalProperties: false`

This is not intended to replace a full JSON Schema implementation. It provides
an early deterministic rejection layer before tool handlers run.

## Verification integration

YiSang accumulates structured action evidence in:

```python
EngineResult.metadata["action_results"]
```

before verification. `ActionEvidenceVerifier` can reject denied or errored
actions. Memory proposals are committed only after the configured verifier
returns `PASS`.

## Security invariant

> Reasoning may request authority; reasoning never creates authority.

The source of execution authority is YiSang policy: registered tools, selected
E.G.O capabilities, permissions, explicit side-effect configuration, and
bounded runtime rules.
