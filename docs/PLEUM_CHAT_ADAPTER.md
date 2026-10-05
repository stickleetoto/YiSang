# PleumRouter Chat Adapter

YiSang supports a dedicated `pleum-chat` upstream mode for Codex.

## Why this mode exists

PleumRouter accepts OpenAI Responses requests for Codex compatibility, but its
Responses adapter documents several Codex fields — including `reasoning` — as
accepted but ignored. It also converts only function tools.

YiSang already has a Responses-to-Chat bridge that can normalize Codex tools and
tool continuations. `pleum-chat` uses that bridge intentionally:

```text
Codex /v1/responses
        |
        v
YiSang Responses -> Chat adapter
        |
        | reasoning_effort / reasoning_mode
        | OpenAI chat function tools
        v
PleumRouter /v1/chat/completions
        |
        v
GPT reasoning model
```

This keeps YiSang's public interface compatible with Codex while sending
PleumRouter the reasoning controls on the route where PleumRouter documents them
as supported.

## Server example

```powershell
cd "D:\Users\leejy\Downloads\project\dev\YiSang"
.\.venv\Scripts\Activate.ps1

$env:YISANG_UPSTREAM_API_KEY="plm_..."

.\.venv\Scripts\python.exe -m yisang.server.__main__ `
  --host 127.0.0.1 `
  --port 18731 `
  --model yisang-luna `
  --upstream-base-url "https://apirouter.pleum.ai/v1" `
  --upstream-model "gpt-6-luna" `
  --upstream-wire-api pleum-chat `
  --reasoning-effort high `
  --reasoning-mode standard `
  --upstream-timeout 1800 `
  --upstream-min-interval 3 `
  --upstream-rate-limit-backoff 2 `
  --upstream-rate-limit-max-backoff 60 `
  --memory ".\data\yisang-luna.db" `
  --ego-root ".\ego" `
  --project "D:\Users\leejy\Downloads\project\dev\devseat-cognitive-guard" `
  --tool-profile full `
  --codex-context-window 32768
```

## Behavior

- Codex still talks to YiSang through `/v1/responses`.
- YiSang converts messages, function-call history, namespaces, and custom tools
  into OpenAI Chat Completions function-tool shape.
- YiSang sends configured `reasoning_effort` and `reasoning_mode` as
  top-level Chat Completions fields.
- When reasoning is enabled, YiSang removes `temperature` and `top_p` from
  the bridged request.
- The current bridge buffers the upstream Chat completion and then emits the
  canonical Responses/SSE events expected by Codex. True incremental Chat-to-
  Responses streaming remains future work.
- The existing local 429/transient-failure governor still wraps the PleumRouter
  request path.

## Wire modes

- `chat-completions`: generic/local OpenAI-compatible Chat backend. YiSang
  does not force reasoning controls.
- `responses`: native Responses backend. YiSang preserves the Responses
  request and writes configured reasoning under `reasoning`.
- `pleum-chat`: PleumRouter-specific compatibility path. Codex Responses are
  translated to Chat Completions and reasoning controls are sent as documented
  PleumRouter Chat fields.
