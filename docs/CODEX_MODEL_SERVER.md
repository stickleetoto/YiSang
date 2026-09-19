# YiSang as a Codex Model Backend

## Goal

Run Codex with YiSang as the configured model provider:

~~~text
Codex agent harness
      |
      | OpenAI Responses API
      v
YiSang model server
      |
      +-- Identity / state
      +-- Memory retrieval
      +-- E.G.O routing
      +-- Context compilation
      +-- small-model tool-call repair
      |
      v
Llama / Qwen / other OpenAI-compatible local model
~~~

Codex keeps shell execution, sandboxing, approvals, and client-tool dispatch.
YiSang is the persistent cognitive layer in front of the replaceable model.

## Current verified path

The following path has been manually verified on Windows with Codex 0.154.0,
YiSang, Ollama, and Llama 3.2 3B:

~~~text
Codex
 -> /v1/responses
 -> YiSang
 -> Ollama Chat Completions
 -> Llama 3.2 3B
 -> YiSang tool-call normalization/recovery
 -> Codex exec_command
 -> workspace-write Windows sandbox
 -> PowerShell 7
 -> real file write
~~~

## 1. Start the upstream local model

Example Ollama endpoint:

~~~text
http://127.0.0.1:11434/v1
~~~

Example model:

~~~text
llama3.2:3b
~~~

## 2. Start YiSang

Install the checkout:

~~~powershell
python -m pip install -e .[dev]
~~~

Then run:

~~~powershell
yisang-model-server `
  --upstream-base-url http://127.0.0.1:11434/v1 `
  --upstream-model "llama3.2:3b" `
  --model yisang-llama `
  --tool-profile codex-small `
  --codex-context-window 4096
~~~

The context-window value must describe the real upstream model configuration.
Do not advertise a larger context window than the local runtime actually exposes.

Default YiSang endpoint:

~~~text
http://127.0.0.1:18731/v1
~~~

Smoke checks:

~~~powershell
Invoke-RestMethod http://127.0.0.1:18731/health
Invoke-RestMethod http://127.0.0.1:18731/v1/models
Invoke-RestMethod http://127.0.0.1:18731/v1/codex/models
~~~

The endpoints have different purposes:

- `/v1/models`: OpenAI-compatible discovery surface.
- `/v1/codex/models`: Codex-native model metadata catalog.

## 3. Generate Codex model metadata

Codex 0.154.0 supports a startup-only `model_catalog_json` file. Unknown
custom model slugs otherwise fall back to generic metadata and emit:

~~~text
Model metadata for `yisang-llama` not found.
Defaulting to fallback metadata...
~~~

Generate a YiSang catalog directly into the active Codex home:

~~~powershell
$env:CODEX_HOME = "$env:USERPROFILE\.codex-yisang-test"

yisang-codex-catalog `
  --model yisang-llama `
  --context-window 4096 `
  --output "$env:CODEX_HOME\yisang-models.json"
~~~

The generator targets the Codex 0.154 catalog shape and supplies conservative
metadata for a text-only local model.

## 4. Configure Codex

Example `config.toml`:

~~~toml
model = "yisang-llama"
model_provider = "yisang"
model_catalog_json = "yisang-models.json"
approval_policy = "never"
sandbox_mode = "workspace-write"

[windows]
sandbox = "unelevated"

[agents]
enabled = false

[features]
goals = false
multi_agent = false
multi_agent_v2 = false

[model_providers.yisang]
name = "YiSang Local"
base_url = "http://127.0.0.1:18731/v1"
wire_api = "responses"
requires_openai_auth = false
~~~

Relative `model_catalog_json` paths are resolved from the Codex config home.

Restart Codex after changing the catalog. Codex applies this catalog at startup.

## Tool ownership

YiSang intentionally does not execute Codex client tools itself.

~~~text
Codex tool schema
      |
      v
YiSang filters/normalizes for the local model
      |
      v
local model chooses a tool
      |
      v
YiSang emits a Responses function_call
      |
      v
Codex executes the tool
~~~

With `--tool-profile codex-small`, YiSang currently exposes only a small
coding surface to the local model and enables conservative textual tool-call
recovery. Unknown tool names are not promoted.

## Responses bridge

Codex 0.154 uses the Responses wire API for custom providers. YiSang accepts
`POST /v1/responses`, translates the request into an upstream Chat
Completions request, waits for the completed local-model response, then emits
Codex-compatible Responses JSON or SSE events.

This is currently buffered bridging, not true upstream token streaming.

## Current protocol surface

Implemented:

~~~text
GET  /health
GET  /v1/models
GET  /v1/codex/models
POST /v1/chat/completions
POST /v1/responses
~~~

Current limitations:

- Responses bridging buffers the upstream completion before emitting events.
- tokenizer-aware accounting for YiSang-injected context is not exact.
- the built-in server has no remote authentication/TLS layer.
- one running server currently exposes one YiSang model alias.
- Codex 0.154 requires a local `model_catalog_json`; newer Codex versions may
  support provider-hosted catalog discovery separately.

## Security boundary

The server binds to `127.0.0.1` by default. Keep it loopback-only unless a
separate authentication/TLS boundary is intentionally added.

The core invariant remains:

> YiSang augments cognition and persistent state; Codex retains client-tool
> execution authority.
