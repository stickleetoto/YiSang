# YiSang Roadmap

> **Mission:** build a persistent, model-independent agent runtime in which the attached LLM is replaceable while identity, memory, capability, goals, and verified experience remain.

YiSang is not a model wrapper whose state disappears when the model changes. The long-term target is a persistent agent substrate that survives model swaps, process restarts, backend changes, and context-window limits without letting the attached model become the source of truth.

---

## 0. Core thesis

~~~text
Models are replaceable.
Memory and capability remain.
~~~

Target boundary:

~~~text
             Codex / UI / Agent Harness
                      |
                      | OpenAI-compatible API
                      v
                +-------------+
                |   YiSang    |
                |-------------|
                | Identity    |
                | State       |
                | Memory      |
                | E.G.O       |
                | Context     |
                | Goals       |
                | Recovery    |
                | Library     |
                +------+------+ 
                       |
             +---------+---------+
             |         |         |
             v         v         v
          Llama      Qwen      future
~~~

Codex or another harness may own shell execution, sandboxing, approvals, and tool dispatch. YiSang owns persistent agent state and the logic that compiles that state into model-visible context.

---

## 1. Non-negotiable invariants

1. YiSang is not the attached base model.
2. Engine replacement must not reset identity, memory, goals, or capabilities.
3. Model output is never authoritative durable memory by itself.
4. Durable writes pass through proposal, validation, provenance, and governance.
5. Session history is working context, not the authoritative memory store.
6. E.G.O is external capability data, not model weights.
7. Model-proposed actions do not create execution authority.
8. Side effects require an explicit execution boundary.
9. Tool output is evidence, not instruction authority.
10. Tool loops are bounded by attempts, time, and/or token budgets.
11. Read-side indexes may be rebuilt; the authoritative store must survive independently.
12. Core interfaces must remain independent of any single model vendor, SDK, agent framework, or protocol.
13. Local runtime context and model-visible context must remain separable.
14. Successful experience may be promoted into capability only after validation.
15. A persistent agent must recover after interruption without repeating irreversible side effects.

---

## 2. Current baseline — v0.3

The v0.3 line has crossed the first important integration milestone: YiSang can act as a custom model backend for Codex and preserve a real tool-execution loop.

Current foundation includes:

- OpenAI-compatible model server
- /v1/chat/completions
- /v1/responses bridge for Codex
- SSE Responses event generation
- SQLite-backed MemoryPort
- model-agnostic context budget handling
- deterministic context rendering
- E.G.O loading from manifest.json + SKILL.md
- engine-swap invariance probe
- typed tool registry and ActionGate
- bounded tool-feedback loop
- read-only workspace confinement
- schema-guided tool argument normalization
- small-model Codex tool profile
- recovery of textual tool calls emitted by weak local models
- Windows Codex sandbox execution through PowerShell 7
- manually verified E2E path:
  Codex -> YiSang -> Llama 3.2 3B -> exec_command -> Windows sandbox -> file write

The current technical problem is no longer basic connectivity. The next stages are about reliability, governed memory, continuity, and experience.

---

# Phase A — Stabilize the agent harness

## v0.3.1 — Codex / small-model stabilization

### Objective

Turn the current successful E2E path into a repeatable and testable baseline before adding large new subsystems.

### Required work

#### Model metadata

- add a Codex-compatible model catalog entry for YiSang models
- remove fallback metadata warnings
- declare realistic context-window and capability information
- test metadata loading against the actual Codex version used in development

#### Completion detection

Add a runtime policy:

~~~text
tool result
  -> inspect goal
  -> verify expected effect
  -> goal satisfied?
       yes -> terminate
       no  -> continue
~~~

A successful tool call must not be followed by unrelated hallucinated work.

#### Structured tool failures

Introduce a typed internal failure model:

~~~text
ToolFailure
  category:
    invalid_arguments
    permission
    environment
    transient
    execution
    timeout
    verification
  retryable
  blame
  recovery_hint
  evidence
~~~

The model may see a compact recovery view, while the full failure record remains local runtime state.

#### Repeatability

Create a repeated E2E suite with cases such as:

- read a file
- write an exact file
- edit one line
- create a directory
- inspect git status
- fail on a missing file and recover
- stop after the requested outcome exists

Run each case multiple times and record:

- success rate
- tool-call count
- malformed-call rate
- retry count
- completion-after-success rate
- wall-clock latency
- context size

### Exit criteria

- no model-metadata fallback warning
- at least 90% success on the local baseline suite with the chosen small model
- no duplicate side effect after verified success
- unknown textual tool calls are never promoted
- malformed known calls are either normalized safely or rejected
- success termination avoids unrelated post-success actions

### Non-goals

- autonomous long-horizon planning
- multi-agent orchestration
- self-modifying skills
- distributed persistence

---

# Phase B — Build governed persistent memory

## v0.4 — Governed Memory

> Status: **VALIDATED**. See `docs/V04_CLOSEOUT.md`, `docs/IMPLEMENTATION_FREEZE.md`, and `docs/VALIDATION_2026-09-19.md`.

### Objective

Move from "persistent database exists" to "the agent has a durable, inspectable, and governed memory system."

### Memory classes

Use logical classes without requiring separate physical databases:

~~~text
Memory
  Episodic   - what happened
  Semantic   - what is known
  Procedural - how to do something
  Working    - temporary/session-only state
~~~

### Authoritative record

A durable memory record should evolve toward:

~~~text
memory_id
memory_type
content
created_at
updated_at
source_id
source_type
evidence_ref
confidence
trust_class
importance
writer
mutation_history
validation_state
last_used_at
success_count
failure_count
schema_version
~~~

### Memory write pipeline

~~~text
model/session/tool evidence
        |
        v
MemoryProposal
        |
        v
dedupe / provenance / trust
        |
        v
quarantine if required
        |
        v
validator
        |
        v
governance
        |
        v
authoritative commit
~~~

The attached model must never directly mutate durable memory.

### SessionPort

Introduce a vendor-neutral SessionPort for replay-oriented conversation state.

~~~text
SessionPort
   -> temporary history
   -> Context Compiler

MemoryPort
   -> governed durable state
~~~

A session may create a MemoryProposal, but session persistence must never bypass durable-memory governance.

### Read-side projections

The authoritative store remains separate from retrieval optimizations:

~~~text
Authoritative MemoryPort
        |
        +--> lexical / FTS projection
        +--> vector projection
        +--> timeline projection
        +--> optional entity-event projection
~~~

Every projection item must retain enough provenance to point back to the authoritative record.

### Retrieval strategy

Do not assume vectors solve all memory retrieval. Benchmark combinations of:

- exact / structured lookup
- SQLite FTS / BM25
- vector retrieval
- recency
- importance
- goal-aware reranking
- procedural-memory retrieval

Vector databases and embeddings remain replaceable indexes, never the source of truth.

### Memory security

Treat persistent-memory poisoning as a first-class threat.

Add:

- trust classification
- provenance requirements
- quarantine state
- mutation authorization
- invalidation / revocation
- memory-source visibility in retrieval
- optional untrusted-memory annotation
- tests where malicious instructions are stored in low-trust memory and must not gain execution authority later

### Evaluation

Build an internal memory suite inspired by LongMemEval-V2, EvoMemBench, and long-term memory poisoning research.

Initial suite:

- 10 static/dynamic knowledge cases
- 10 workflow/gotcha cases
- 10 cross-session execution cases
- 10 poisoned/untrusted-memory cases

Compare:

- memory disabled
- session only
- retrieval memory
- retrieval + procedural memory
- retrieval + procedural memory + provenance policy

Record:

- answer/task success
- evidence correctness
- retrieval precision
- context tokens
- write count
- latency
- poisoning escape rate

### Exit criteria

- authoritative memory can be exported and restored
- all persistent writes have provenance
- session state cannot directly mutate durable memory
- retrieval indexes can be deleted and rebuilt
- poisoning tests cannot grant execution authority from untrusted memory
- internal benchmark produces stable reproducible results

---

# Phase C — Make identity survive engine changes

## v0.5 — Identity Continuity

> Status: **live two-engine validation passed / saved-report closeout check pending**. See `docs/V05_CLOSEOUT.md` and `docs/VALIDATION_2026-09-19.md`.

### Objective

Prove the central YiSang claim:

> changing the reasoning engine changes reasoning quality, not the identity of the persistent agent.

### Identity snapshot

Create an explicit, versioned identity/state snapshot containing references to:

- identity charter
- active goals
- durable memory root/version
- E.G.O capability registry
- Library root/version
- policy version
- runtime compatibility version
- engine-independent preferences/state
- schema version
- migration history

### Engine-swap invariance suite

~~~text
snapshot A
  -> Llama
  -> Qwen
  -> another local model
~~~

All engines must observe the same authoritative identity, goals, memories, capabilities, Library, and policy boundary.

Answer style and reasoning quality may differ. Persistent state may not silently diverge.

### Restore validation

On startup:

1. load snapshot
2. verify schema
3. verify referenced stores
4. run compatibility migrations if necessary
5. reject partial or contradictory state
6. record restore evidence

### Exit criteria

- engine swap does not create a new identity
- restart + restore resumes the same goal and state
- schema migrations are explicit and testable
- snapshot corruption is detected
- continuity test passes across at least two different engines

---

# Phase D — Build Roland as a context-on-demand library

## v0.6 — Roland Library

### Objective

Turn YiSang external knowledge into a structured library that can grow without forcing all knowledge into every prompt.

### Design

~~~text
Roland
  |
  +--> Book Index
  |      title
  |      description
  |      tags
  |      provenance
  |      estimated context cost
  |
  +--> Selected Book
         summary / TOC
         chapters
         evidence
         resources
~~~

### Progressive disclosure

Use the architectural idea behind Agent Skills:

1. metadata stays cheap to discover
2. full instructions/content load only after selection
3. large resources load only when required

Do not make Agent Skills the YiSang-native storage model. Support adapters when portability is useful.

### Book format

A book should eventually support:

~~~text
book_id
title
description
tags
version
source_refs[]
trust_class
created_at
updated_at
toc
chapters[]
summary
related_books[]
schema_version
~~~

### Retrieval

~~~text
goal/query
 -> metadata shortlist
 -> book selection
 -> chapter selection
 -> evidence extraction
 -> ContextPack
~~~

### Benchmarks

With 10 / 50 / 100 / 500 books measure:

- metadata context cost
- selection accuracy
- chapter retrieval precision
- total prompt tokens
- latency
- answer/task success

### Exit criteria

- hundreds of books do not require loading hundreds of full prompts
- every extracted knowledge fragment points to a source/book
- a missing/rebuilt retrieval index does not destroy books
- book access can be audited
- YiSang can answer using a selected book without injecting the entire Library

---

# Phase E — Convert verified experience into durable capability

## v0.7 — Experience Promotion

### Objective

Allow YiSang to improve from successful experience without turning raw logs or model hallucinations into permanent skills.

### Promotion pipeline

~~~text
Raw Episode
    |
    v
Lesson Candidate
    |
    v
Generalize
    |
    v
Validator
    |
    v
Replay / test
    |
    v
Promotion Gate
    |
    v
Durable Skill / Knowledge
~~~

### Failure learning

Failure is evidence, not a skill.

~~~text
failure
 -> anti-pattern candidate
 -> reproduce
 -> characterize trigger
 -> validate workaround
 -> durable warning
~~~

### Promotion rules

A candidate should carry:

- source episodes
- trigger conditions
- proposed procedure
- validation tests
- evidence
- success count
- failure count
- scope
- risk class
- version

Automatic promotion of privileged or security-sensitive capabilities should be prohibited.

### E.G.O integration

Validated procedural knowledge may become:

- E.G.O instruction refinement
- a new reusable procedure
- a Library entry
- an anti-pattern warning
- a tool-routing heuristic

The canonical format remains YiSang-native. Agent Skills or plugin formats remain interoperability layers.

### Exit criteria

- raw conversation text is not promoted directly
- promoted skills have reproducible evidence
- a promoted skill can be invalidated or rolled back
- failed candidates remain distinguishable from accepted capabilities
- capability changes are versioned

---

# Phase F — Durable goals, journals, and recovery

## v0.8 — Goal / Recovery Runtime

### Objective

Allow YiSang to stop, restart, fail, and resume long-running work without losing state or repeating irreversible effects.

### Goal model

~~~text
Goal
  id
  description
  status
  created_at
  milestones[]
  completed_work[]
  blockers[]
  next_action
  exit_condition
  attempt_budget
  time_budget
  token_budget
  failure_budget
~~~

### RunContext vs ContextPack

Formalize the separation:

~~~text
RunContext          ContextPack
-----------         -----------
request id          identity instructions
auth handles        selected memory
policy state        selected E.G.O
storage handles     selected Library evidence
budgets             task input
telemetry           exposed tool schemas
approval state
~~~

RunContext remains local unless an explicit exposure rule allows a field into ContextPack.

### RunJournal

Introduce a deterministic journal:

~~~text
run_id
step_id
goal_id
input_hash
state
tool_or_model_action
side_effect_id
result_ref
verification
retry_count
created_at
updated_at
~~~

### Side-effect receipts

The recovery model must distinguish:

~~~text
planned but not executed
executed but result not processed
verified
failed
unknown
~~~

Irreversible work should have a stable side-effect identifier or receipt when practical.

### Checkpoints

Recommended checkpoints:

~~~text
compile context
 -> checkpoint
model call
 -> checkpoint
tool proposal
 -> checkpoint
approval
 -> checkpoint
side effect
 -> receipt + checkpoint
verification
 -> checkpoint
memory proposal
 -> checkpoint
governance
 -> commit
~~~

### Recovery classifier

~~~text
failure
  transient
  bad_arguments
  permission
  environment
  missing_capability
  verification_failure
  impossible
~~~

Policy decides whether to retry, rewrite, use an alternate tool, request input, or stop.

No infinite retry loops.

### MCP mapping

Support long-running external work through an internal abstraction such as:

~~~text
CapabilityExecution
  id
  capability_id
  state
  created_at
  updated_at
  result_ref
  evidence_refs[]
  approval_state
~~~

MCP Tasks may map onto this abstraction through an adapter. MCP Tasks must not become the canonical YiSang runtime representation.

### Exit criteria

- a killed process can resume from a safe checkpoint
- already-completed side effects are not blindly repeated
- goals survive restart
- failure recovery is budgeted and typed
- long-running work can be represented without holding one transport call open forever

---

# Phase G — Multi-engine and BIO interoperability

## v0.9 — Multi-engine / BIO

### Objective

Prove that YiSang remains portable across reasoning engines and memory backends.

### Engine matrix

Continuously test more than one engine family:

~~~text
YiSang
  +-- Llama-class local model
  +-- Qwen-class local model
  +-- optional cloud model adapter
  +-- future engines
~~~

### MemoryPort adapters

Keep:

~~~text
InMemoryMemoryPort
SQLiteMemoryPort
BioMemoryPort
~~~

BIO remains optional. YiSang must work without BIO.

### Protocol adapters

Potential adapters:

- OpenAI Chat Completions
- OpenAI Responses
- MCP
- Agent Skills import/export
- future plugin packaging

Adapters sit outside the core state model.

### Policy authorization

Evolve ActionGate toward an explicit authorization model inspired by principal/action/resource/context systems:

~~~text
principal: engine / ego / user
action:    memory.write / tool.run / library.mutate
resource:  memory/... / capability/... / goal/...
context:   trust / approval / risk / source / environment
~~~

A policy engine may be implemented internally first. External systems such as Cedar are references, not mandatory dependencies.

### Optional temporal projections

Experiment with timeline/entity-event projections for changing facts. These remain rebuildable read-side indexes over authoritative memory.

### Exit criteria

- same snapshot runs on at least two engines
- memory backend can be swapped without changing core semantics
- BIO adapter can be disconnected without disabling YiSang
- policy behavior is independent of the attached model
- protocol adapters remain replaceable

---

# Phase H — Persistent Agent release

## v1.0 — Continuity Release

### Definition of done

YiSang v1.0 is defined by continuity, not feature count.

The following scenarios must work:

~~~text
LLM removed
 -> another LLM attached
 -> same identity / goals / memory / capabilities

process killed
 -> restart
 -> same active work recovered

machine rebooted
 -> restore
 -> same agent state

retrieval index deleted
 -> rebuild
 -> no authoritative memory loss

memory backend migrated
 -> continuity preserved

Library index rebuilt
 -> source books preserved

E.G.O upgraded
 -> capability history/version remains inspectable

side effect completed before crash
 -> recovery does not blindly repeat it
~~~

### YISANG_CONTINUITY_TEST

A release-level test should:

1. initialize YiSang with Engine A
2. create governed durable memories
3. register E.G.O capabilities
4. create a Library
5. create an active goal
6. complete at least one verified external action
7. persist snapshot/journal
8. terminate the process
9. replace Engine A with Engine B
10. restore state
11. continue the active goal
12. retrieve old knowledge and procedural memory
13. use an existing capability
14. verify that prior side effects are not duplicated
15. export and verify the final continuity report

### Release metrics

Track at minimum:

- continuity pass/fail
- task success rate
- repeatability variance
- malformed tool-call rate
- memory retrieval precision
- evidence correctness
- poisoning escape rate
- restore latency
- context tokens
- tool count
- retry count
- side-effect duplication count

---

# 3. Cross-cutting technology tracks

## A. Context efficiency

- metadata-only E.G.O discovery
- progressive disclosure
- context-budget accounting
- reversible compaction
- goal-aware retrieval
- lazy Library loading

Target report:

~~~text
ContextBudgetReport
  total_input
  identity
  memory
  ego
  library
  tools
  conversation
  compacted
  dropped
~~~

## B. Provenance

Every durable artifact should eventually support provenance:

- memory records
- Library books
- skills / E.G.O
- snapshots
- promoted experience
- side-effect receipts

Long-term snapshot hardening may use manifest hashes, schema versions, migration versions, and signed provenance where useful.

SLSA / Sigstore style provenance is a future reference, not an immediate dependency.

## C. Observability

Instrument:

- model latency
- retrieval latency
- tool latency
- verification latency
- retries
- context size
- memory writes
- index rebuilds
- recovery paths

OpenTelemetry is a candidate adapter for traces and metrics, but Core should retain its own telemetry abstraction.

## D. Security

Threat models:

- prompt injection
- tool-output injection
- persistent memory poisoning
- malicious Library source
- capability escalation
- forged provenance
- snapshot tampering
- duplicated side effects after crash

Security-relevant state must remain outside model authority.

## E. Evaluation

Prefer reproducible local benchmarks over architecture claims.

Important evaluation families:

- tool-use repeatability
- memory recall
- dynamic-state tracking
- procedural/workflow memory
- cross-session execution
- poisoning resistance
- context efficiency
- engine-swap continuity
- recovery after interruption

---

# 4. Technology references

## Internal archive

Relevant research is already collected in:

- stickleetoto/AI-Tech-Archive/research/2026-09-12-project-tech-20.md
- stickleetoto/AI-Tech-Archive/research/2026-09-15-cross-project-tech-radar-20-v6.md
- stickleetoto/AI-Tech-Archive/research/2026-09-18-tech-scout-30.md
- stickleetoto/AI-Tech-Archive/index/TECH_RADAR.md
- docs/TECH_RADAR_2026-09-17.md

## External references to continue tracking

- Agent Skills progressive disclosure
- Agent Plugins packaging
- MCP 2026-07-28 stateless core
- MCP Tasks
- OpenAI Agents context/session separation
- LangGraph durable execution/checkpoint patterns
- Temporal durable execution patterns
- LongMemEval-V2
- EvoMemBench
- provenance-oriented memory projections
- sqlite-vec / embedded local vector retrieval
- temporal/entity-event graph projections
- Cedar-style authorization modeling
- SLSA / Sigstore-style provenance and attestation

External projects are references and interoperability targets. None should become a hard Core dependency without a separate decision.

---

# 5. Implementation order

~~~text
v0.3.1  Harness stabilization
   |
   v
v0.4    Governed persistent memory
   |
   v
v0.5    Identity continuity
   |
   v
v0.6    Roland Library
   |
   v
v0.7    Experience promotion
   |
   v
v0.8    Goal / recovery runtime
   |
   v
v0.9    Multi-engine / BIO
   |
   v
v1.0    Persistent Agent continuity release
~~~

Each phase should contain:

1. implementation tasks
2. tests
3. benchmarks
4. exit criteria
5. migration notes
6. explicit non-goals

Do not move to the next phase only because code exists. Move when the exit criteria are demonstrated.

---

# 6. Immediate next work

v0.4 is validated. v0.5 has passed the real cross-family continuity run; the current task is the final saved-report closeout check before promotion from `0.5.0rc1`.

Order:

1. run `yisang-eval-continuity-check` against the saved `artifacts/continuity-v05.json`
2. if ready, promote package version from `0.5.0rc1` to `0.5.0`
3. create the validated v0.5 baseline
4. begin v0.6 Roland
