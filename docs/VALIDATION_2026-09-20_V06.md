# YiSang v0.6 Roland Library — Validation Evidence

Date: 2026-09-20

Status: **VALIDATED**

This document records the live v0.6 closeout evidence produced by
`scripts/v06_closeout.ps1`.

## Environment

- OpenAI-compatible runtime: Ollama
- base URL: `http://127.0.0.1:11434/v1`
- source model: `llama3.2:3b`
- source family: `llama`
- target model: `qwen2.5:1.5b`
- target family: `qwen`
- repeats: 3
- temperature: 0.0
- max response tokens: 64

## Cross-family continuity result

Saved report:

- `artifacts/v06-closeout/continuity-v06.json`

Observed result:

- case count: 3
- pass rate: 1.0
- all passed: true
- v0.6 continuity closeout checker: `ready=true`
- closeout errors: none
- Library probe evidence: true
- source engine exercised: yes
- target engine exercised: yes
- continuity fingerprint preserved: yes
- stable Roland `knowledge_ref` retrieved before engine replacement: yes
- stable Roland `knowledge_ref` retrieved after restore: yes

Recorded restore/probe summary from the run:

- mean restore latency: 0.8361000000149943 ms
- reported p95 restore latency: 0.8713999995961785 ms
- mean probe latency: 10635.279633333994 ms
- reported p95 probe latency: 1503.9800999984436 ms

The percentile values above are preserved exactly as emitted by the v0.6
validation binary. The pass/fail gate does not depend on a latency threshold.
A small-sample percentile estimator correction is tracked separately after the
validated v0.6 freeze so that the validated runtime/evidence boundary remains
unchanged.

## Roland scale benchmark

Saved report:

- `artifacts/v06-closeout/library-v06.json`

All required scales passed with top-1 selection accuracy 1.0.

| Books | Index build ms | Mean search ms | Reported p95 search ms | Mean delivery chars |
| ---: | ---: | ---: | ---: | ---: |
| 10 | 0.29510000240406953 | 0.053219999608700164 | 0.06349999966914766 | 412.0 |
| 50 | 1.0753999995358754 | 0.044565999633050524 | 0.04809999882127158 | 416.8 |
| 100 | 2.0847999985562637 | 0.04438199983269442 | 0.0518000015290454 | 417.4 |
| 500 | 11.683900000207359 | 0.05223799969826359 | 0.06759999814676121 | 422.68 |

Scale checker result:

- required scales: 10 / 50 / 100 / 500
- all passed: true
- checker: `ready=true`
- errors: none

## Composite closeout

`yisang-eval-v06-closeout` returned:

~~~text
ready: true
errors: []
continuity.ready: true
continuity.pass_rate: 1.0
library.ready: true
library.all_passed: true
~~~

The final script emitted:

~~~text
YiSang v0.6 closeout evidence is READY.
~~~

## Exit-criteria mapping

| v0.6 exit criterion | Evidence |
| --- | --- |
| hundreds of Books do not require loading hundreds of full prompts | 500-Book benchmark passed; mean delivered Library context 422.68 chars |
| every extracted knowledge fragment points to a source/Book | Library delivery preserves Book/source refs and stable knowledge refs; regression suite passed |
| missing/rebuilt retrieval index does not destroy Books | authoritative LibraryPort + rebuildable CompactLibraryIndex and continuity restore tests passed |
| Book access can be audited | stable knowledge refs, provenance/trust/validation metadata, and used knowledge refs are recorded |
| selected Book knowledge can be used without injecting the entire Library | request-aware retrieval/delivery path passed at every required scale |
| Library survives reasoning-engine replacement | Llama -> Qwen live continuity: 3/3 passed with source/target knowledge-ref retrieval |

## Closeout decision

YiSang v0.6 Roland Library satisfies its implemented closeout gates and is
promoted to `0.6.0`.

The validated implementation should be frozen separately from subsequent
measurement-only fixes and v0.7 development.
