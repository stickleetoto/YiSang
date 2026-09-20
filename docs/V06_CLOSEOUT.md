# YiSang v0.6 Roland Library — Closeout Procedure

Status: **PREPARED — live cross-family evidence pending**

v0.6 closeout requires both:

1. live cross-family continuity evidence proving Roland knowledge survives restore and engine replacement;
2. deterministic 10 / 50 / 100 / 500 Book scale evidence.

## One-command Windows run

From an activated YiSang virtual environment:

~~~powershell
.\scripts\v06_closeout.ps1 \
  -SourceBaseUrl "http://127.0.0.1:1234/v1" \
  -SourceModel "<llama-model-id>" \
  -SourceFamily "llama" \
  -TargetBaseUrl "http://127.0.0.1:1234/v1" \
  -TargetModel "<qwen-model-id>" \
  -TargetFamily "qwen"
~~~

Use different base URLs when the two models are hosted by separate servers.
If an endpoint requires a key, pass `-SourceApiKey` or `-TargetApiKey`.

The script writes:

- `artifacts/v06-closeout/continuity-v06.json`
- `artifacts/v06-closeout/library-v06.json`

and finishes with the composite `yisang-eval-v06-closeout` gate.

## Individual commands

### Live continuity + Roland retrieval

~~~powershell
yisang-eval-continuity \
  --source-base-url "<source-openai-compatible-v1>" \
  --source-model "<source-model>" \
  --source-family "llama" \
  --target-base-url "<target-openai-compatible-v1>" \
  --target-model "<target-model>" \
  --target-family "qwen" \
  --repeats 3 \
  --output ".\artifacts\v06-closeout\continuity-v06.json"
~~~

Validate it:

~~~powershell
yisang-eval-continuity-check \
  --input ".\artifacts\v06-closeout\continuity-v06.json" \
  --phase v0.6 \
  --min-repeats 3
~~~

The v0.6 gate requires:

- different source and target engine-family labels;
- all repeated continuity cases pass;
- source and target models are both exercised;
- continuity fingerprint is preserved;
- Library snapshot reference is preserved;
- the expected stable `knowledge_ref` is retrieved before the swap;
- the same expected stable `knowledge_ref` is retrieved after restore.

### Roland scale benchmark

~~~powershell
yisang-eval-library --output ".\artifacts\v06-closeout\library-v06.json"
yisang-eval-library-check --input ".\artifacts\v06-closeout\library-v06.json"
~~~

Required scales are 10, 50, 100, and 500 Books.

The checker requires:

- every required scale is present;
- top-1 selection accuracy is 1.0;
- query count is positive;
- index/search timings are non-negative;
- delivered Library context remains within the 4,000-character mean budget;
- index term/posting statistics are non-empty.

A manual GitHub Actions workflow, `v0.6 Roland benchmark`, can also produce
repeatable CI-side scale reports for Python 3.11 and 3.12.

## Composite closeout gate

~~~powershell
yisang-eval-v06-closeout \
  --continuity ".\artifacts\v06-closeout\continuity-v06.json" \
  --library ".\artifacts\v06-closeout\library-v06.json" \
  --min-repeats 3
~~~

v0.6 is ready for closeout only when this command returns `"ready": true`.

## Safety-budget invariant

Under severe Library context pressure:

1. optional details are removed first;
2. positive complements are removed before guardrails;
3. model-visible knowledge text is compacted;
4. when primary advice and a guardrail cannot both fit, the guardrail wins.

The guardrail retains its `avoid_when` and provenance/trust boundary.

## Remaining closeout action

The repository can prepare and validate the harness in CI, but the real
Llama-to-Qwen continuity report requires the configured local or reachable
OpenAI-compatible endpoints. After the live report and scale report are saved,
run the composite gate and record the evidence in the v0.6 validation document.
