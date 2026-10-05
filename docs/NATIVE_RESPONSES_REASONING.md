# Native Responses upstream for GPT-6 reasoning

YiSang can use two upstream protocols:

- `chat-completions`: legacy/default bridge for local OpenAI-compatible models
  such as Ollama.
- `responses`: native OpenAI Responses forwarding for reasoning models and
  tool-heavy Codex workflows.

The native path exists so Codex tool schemas, namespace tools, function-call
continuations, reasoning items, and usage details do not have to round-trip
through Chat Completions.

## GPT-6 Luna through PleumRouter

Set the PleumRouter key only in the process that launches YiSang:

~~~powershell
$env:YISANG_UPSTREAM_API_KEY = "plm_..."
~~~

Start YiSang:

~~~powershell
yisang-model-server `
  --host 127.0.0.1 `
  --port 18731 `
  --model yisang-luna `
  --upstream-base-url "https://apirouter.pleum.ai/v1" `
  --upstream-model "gpt-6-luna" `
  --upstream-wire-api responses `
  --reasoning-effort xhigh `
  --reasoning-mode pro `
  --upstream-timeout 1800 `
  --memory ".\data\yisang-luna.db" `
  --ego-root ".\ego" `
  --project "$PWD" `
  --tool-profile full `
  --codex-context-window 32768
~~~

Use `--tool-profile full` when Codex must expose MCP tools such as mcp-hand.
The `codex-small` profile intentionally allows only the compact local coding
surface and will hide unrelated MCP namespace tools.

Health inspection:

~~~powershell
Invoke-RestMethod http://127.0.0.1:18731/health
~~~

Expected fields include:

~~~text
status             ok
model              yisang-luna
upstream_wire_api  responses
reasoning_effort   xhigh
reasoning_mode     standard
tool_profile       full
rate_limit         ...
~~~

## Reasoning policy

Configured server values override client-requested `reasoning.effort` and
`reasoning.mode`. Other reasoning fields, such as a requested summary mode,
are preserved.

When the effective effort is not `none`, YiSang removes sampling controls
that conflict with GPT-6 reasoning requests (`temperature`, `top_p`,
`top_logprobs`, and `logprobs`).

For long agentic development, `xhigh + pro` is the quality-first baseline.
Use `max` only after representative evals show that its additional latency
and token use improve task success enough to justify the cost.

## Compatibility boundary

The default remains `chat-completions`. Existing local-model workflows do
not change unless `--upstream-wire-api responses` is explicitly selected.

The native Responses path is buffered today: YiSang asks the upstream for a
completed response, rewrites the public model id back to the YiSang alias, and
then emits the existing Codex-compatible Responses/SSE surface. This preserves
native reasoning and tool output items without requiring native upstream token
streaming.

## Provider rate-limit containment

YiSang now treats provider HTTP 429 as rate limiting rather than as a generic
gateway failure.

Behavior:

- upstream 429 is returned to Codex as HTTP 429, not 502;
- Retry-After is preserved when the provider supplies it;
- a local exponential cooldown opens after a provider 429;
- requests arriving during cooldown are rejected locally without touching the
  provider;
- request starts are spaced by upstream-min-interval, which defaults to 2s;
- a successful provider response resets the consecutive-429 strike counter.

This prevents a fast Codex tool loop from turning one provider 429 into a retry
storm. YiSang itself never retries the failed provider request.

For normal long-running Luna development, start with xhigh + standard. Enable
pro only for cases where representative evals show a material quality gain.
