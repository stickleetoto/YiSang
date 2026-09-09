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
      +-- handler error -----------------> ERROR
      |
      v
ActionResult(EXECUTED)
```

## ToolDefinition

Each tool declares:

- stable `tool_id`
- callable handler
- human-readable description
- required E.G.O capabilities
- required permissions
- whether it has side effects

Every tool must require at least one E.G.O capability. This prevents a model
from gaining tool access independently from YiSang's portable capability layer.

## ActionGate

The gate authorizes a proposal only when one selected E.G.O:

1. provides every capability required by the tool; and
2. grants every permission required by the tool.

Filesystem permissions currently form this ordered policy:

```text
none < read < workspace < unrestricted
```

Boolean permissions such as `network` require explicit `true` when the tool
requires them.

## Side effects

`ActionGate(allow_side_effects=False)` is the default.

Therefore a tool marked `side_effecting=True` cannot run until the application
explicitly opts into side effects. Future write/shell tools should remain
side-effecting and should add stronger confirmation policy above this baseline.

## Error containment

Tool exceptions do not crash YiSang. They are converted into:

```text
ActionResult(status="ERROR", error="ExceptionType: message")
```

Denied tools similarly become structured `DENIED` results.

## Verification integration

After execution, YiSang attaches serialized action results to:

```python
EngineResult.metadata["action_results"]
```

before calling the verifier. This allows verifier implementations to judge
claims against deterministic execution evidence without changing the existing
verifier interface.

## Security invariant

The execution layer must preserve this rule:

> Reasoning may request authority; reasoning never creates authority.

The source of execution authority is YiSang policy: registered tools, selected
E.G.O capabilities, permissions, and explicit side-effect configuration.
