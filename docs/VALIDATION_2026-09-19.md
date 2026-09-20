# YiSang Validation Record — 2026-09-19

This record captures the local validation evidence produced against the v0.5.0rc1 line after freeze-permitted validation fixes.

## Repository test suite

Environment:

- Windows
- Python 3.13.4
- project .venv
- editable install of yisang 0.5.0rc1

Result:

~~~text
199 passed in 6.81s
~~~

Status: **PASS**

## v0.4 Governed Memory benchmark

Command:

~~~powershell
yisang-eval-memory --output ".\artifacts\memory-v04.json"
~~~

Result:

~~~text
case_count         : 40
pass_rate          : 1.0
mean_recall        : 1.0
forbidden_hits     : 0
poison_escape_rate : 0.0
exit code          : 0
~~~

Status: **PASS**

## v0.4 authoritative SQLite audit

Representative authoritative store:

~~~text
record_count      : 3
active_count      : 2
invalidated_count : 1
superseded_count  : 1
mutation_count    : 4
schema_versions   : {3=3}
ok                : True
issues            : {}
exit code          : 0
~~~

Status: **PASS**

## v0.5 live cross-family continuity run

Source:

- engine id: llama-source
- family: llama
- model: llama3.2:3b

Target:

- engine id: qwen-target
- family: qwen
- model: qwen2.5:1.5b

Run parameters:

- repeats: 5
- max_tokens: 32
- timeout: 180 seconds

Result:

~~~json
{
  "case_count": 5,
  "pass_rate": 1.0,
  "all_passed": true,
  "source_engine": "llama-source",
  "target_engine": "qwen-target",
  "source_model": "llama3.2:3b",
  "target_model": "qwen2.5:1.5b",
  "source_family": "llama",
  "target_family": "qwen",
  "closeout_ready": true,
  "closeout_errors": []
}
~~~

Status: **LIVE CONTINUITY PASS**

## Saved-report closeout check

The saved continuity report was loaded through the closeout checker with the
following result:

~~~text
ready      : true
errors     : []
case_count : 5
pass_rate  : 1.0
~~~

The report metadata confirmed source `llama3.2:3b` / family `llama`, target
`qwen2.5:1.5b` / family `qwen`, 5 repeats, and `max_tokens=32`.

Status: **PASS**

## Current phase status

- v0.4 Governed Memory: **VALIDATED**
- v0.5 Identity Continuity: **VALIDATED**
- release promotion: **0.5.0**
