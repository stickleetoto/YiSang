# YiSang Tech Radar — 2026-09-17

This note accumulates technical ideas that can strengthen YiSang without violating its core invariant:

> Models are replaceable. Memory and capability remain.

The goal is not to adopt frameworks wholesale. External projects and standards are treated as reference implementations, protocols, benchmarks, and design evidence. YiSang Core should continue to depend on its own interfaces.

## Current architectural anchors

YiSang already separates Identity, Memory, E.G.O / Skills, Context Compilation, Engine backends, Verification, and Governance. The current runtime flow is:

```text
request
 -> retrieve memory
 -> route E.G.O
 -> compile context
 -> call engine
 -> verify
 -> propose memory
 -> governance
 -> commit
 -> response
```

Research below should preserve these rules:

1. Session history is not authoritative long-term memory.
2. LLM output never writes memory directly.
3. A provider SDK may be adapted, but must not become the YiSang Core abstraction.
4. E.G.O capability metadata must remain separable from any single agent/vendor format.
5. Persistent memory should have provenance and governance before optimization indexes are added.
6. Read-side indexes may be rebuilt; the authoritative store must remain recoverable independently of them.

---

## 1. Agent Skills + progressive disclosure

**Status:** ACTION

The Agent Skills open format uses a skill directory with `SKILL.md` as the entry point, plus optional `scripts/`, `references/`, and `assets/`. Its most useful architectural idea for YiSang is progressive disclosure: keep only small capability metadata in always-visible context, load the full instructions only after a capability is selected, and load large resources only when required.

### YiSang mapping

```text
Agent Skill metadata     -> E.G.O discovery metadata
SKILL.md instructions    -> activated E.G.O instruction payload
references/assets        -> lazy-loaded E.G.O resources
scripts/tools            -> capability execution backend
```

Do **not** replace E.G.O with Agent Skills. Instead, add a future adapter/export format so one E.G.O can be represented as an Agent Skill when portability is useful.

### First PoC

- Add a metadata-only E.G.O discovery path.
- Keep `name`, `description`, capability tags, risk class, and approximate context cost always available.
- Load full E.G.O payload only after routing.
- Benchmark context tokens with 10 / 50 / 100 registered E.G.O entries.

**Source:** https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx

---

## 2. Split local runtime context from LLM-visible context

**Status:** ACTION

The OpenAI Agents SDK explicitly separates local run context from the context visible to the model. This is a useful reference distinction for YiSang because permissions, storage handles, governance state, telemetry, secrets, and execution metadata should not automatically be serialized into prompts.

### YiSang mapping

Introduce a conceptual split:

```text
RunContext
  - request id
  - tenant/user scope
  - auth / policy handles
  - storage handles
  - tracing
  - resource budgets
  - approval state

ContextPack
  - selected identity instructions
  - retrieved memory evidence
  - selected E.G.O instructions
  - task input
  - explicitly exposed tool descriptions
```

`RunContext` stays local. `ContextPack` is the only structure compiled for model consumption.

### First PoC

Add tests proving that local-only fields can never appear in serialized model input unless an explicit exposure rule is present.

**Source:** https://openai.github.io/openai-agents-python/context/

---

## 3. Session adapters are working memory, not durable memory

**Status:** ACTION

Current agent SDKs increasingly expose a pluggable session interface. OpenAI Agents SDK sessions, for example, retrieve prior conversation items before a run and persist new run items afterwards; custom session backends can implement the same interface.

YiSang should support this pattern only as **working/session history**, separate from governed durable memory.

### Proposed boundary

```text
ConversationSession
  temporary / replay-oriented history
       |
       v
Context Compiler
       |
       +----> model

MemoryPort
  governed durable memory
       ^
       |
MemoryProposal -> Governance -> Commit
```

A session transcript may generate a `MemoryProposal`, but it must not automatically become durable memory.

### First PoC

Define a small `SessionPort` interface independently of any vendor SDK and add an adapter for one external session implementation later.

**Source:** https://openai.github.io/openai-agents-python/sessions/

---

## 4. Context compaction should be reversible with respect to durable memory

**Status:** ACTION

Long-running agents need context compaction, but prompt compaction and memory consolidation are different operations. Provider SDKs now expose session-history compaction mechanisms; YiSang should treat these as a context-budget optimization only.

### Rule

- Raw durable memory remains governed and provenance-preserving.
- Session/context history may be summarized or compacted.
- Compacted context must carry a pointer to the underlying evidence range or source IDs when practical.
- A compaction failure must not corrupt the durable memory store.

### First PoC

Implement a `ContextBudgetReport` containing:

```text
input tokens
identity tokens
memory tokens
E.G.O tokens
tool schema tokens
conversation tokens
compacted tokens
items dropped
```

Then evaluate fixed-budget compilation at 8k / 16k / 32k contexts.

**Reference:** https://openai.github.io/openai-agents-js/guides/sessions/

---

## 5. MCP 2026-07-28 stateless core

**Status:** ACTION

The 2026-07-28 MCP specification moved the protocol core toward stateless request/response operation. The release also adds Multi Round-Trip Requests, header-based routing, cacheable list results, authorization hardening, and a formal extension framework.

A particularly useful design lesson for YiSang is that transport-level statelessness does not mean application state must disappear. When state is needed, it can be represented by an explicit handle that the model/tool caller passes between requests rather than being hidden inside the transport.

### YiSang implications

- Keep E.G.O/tool execution state explicit.
- Avoid hidden provider-specific session state in Core.
- Represent long-lived tool operations with typed handles.
- Make authorization/policy decisions before dispatch.
- Cache tool manifests independently from tool execution state.

### First PoC

Create an `MCPToolBackend` adapter outside Core that maps YiSang capability calls to the current MCP spec while preserving YiSang-native authorization and verification gates.

**Source:** https://blog.modelcontextprotocol.io/posts/2026-07-28/

---

## 6. MCP Tasks for long-running capability execution

**Status:** EXPERIMENT

The MCP Tasks extension draft allows a tool call to return an asynchronous task handle instead of a final result and defines task retrieval/update/cancel operations. This is relevant to YiSang capabilities that perform long-running research, build, training, or remote execution.

### YiSang mapping

Potential internal abstraction:

```text
CapabilityExecution
  id
  capability_id
  state: queued | running | input_required | succeeded | failed | cancelled
  created_at
  updated_at
  result_ref
  evidence_refs[]
  approval_state
```

The MCP Tasks format should be an adapter target, not the canonical Core model, while the extension remains draft.

**Source:** https://tasks.extensions.modelcontextprotocol.io/specification/draft/tasks

---

## 7. Durable execution + checkpointing as a runtime property

**Status:** EXPERIMENT

LangGraph v1 keeps durable execution, checkpointing, persistence, streaming, and human-in-the-loop as first-class runtime concerns. YiSang should learn from the pattern without depending on LangGraph itself.

### Desired YiSang property

A run should be resumable around side effects:

```text
compile context
 -> checkpoint
 -> model call
 -> checkpoint
 -> tool proposal
 -> approval/gate
 -> side effect
 -> record evidence
 -> verification
 -> memory proposal
 -> governance
 -> commit
```

The important distinction is **replay-safe reasoning state vs irreversible external side effects**.

### First PoC

Add a deterministic `RunJournal` format for one-tool workflows and test recovery after interruption before and after the tool side effect.

**Reference:** https://docs.langchain.com/oss/python/releases/langgraph-v1

---

## 8. Provenance-aware multi-projection memory

**Status:** EXPERIMENT

Agent Zero Memory (2026-08 preprint) describes three parallel memory views: an episodic timeline, an entity-event graph, and hierarchical documentary memory, with source/timestamp/evidence provenance and citation-locked retrieval.

The valuable part for YiSang is **not** to create three authoritative stores. Instead, keep one authoritative MemoryPort and materialize rebuildable read-side projections.

### Proposed shape

```text
Authoritative MemoryPort
        |
        +--> Timeline projection
        +--> Entity/Event graph projection
        +--> Documentary/semantic projection
```

Every projection entry should retain:

```text
memory_id
source_id
timestamp
evidence pointer
projection version
```

If a projection is lost, it can be rebuilt from authoritative memory.

**Source:** https://arxiv.org/abs/2608.29606

---

## 9. Memory evaluation must cover experience, not only retrieval

**Status:** ACTION

Two 2026 benchmarks are directly relevant:

### LongMemEval-V2

451 manually curated questions across five abilities:

- static state recall
- dynamic state tracking
- workflow knowledge
- environment gotchas
- premise awareness

This is useful because a persistent agent must remember how an environment behaves, not merely retrieve user facts.

**Source:** https://arxiv.org/abs/2605.12493

### EvoMemBench

Organizes memory along two axes:

```text
scope:   in-episode | cross-episode
content: knowledge  | execution
```

Its reported results are an important warning: no single memory form dominates every workload, and long-context baselines remain competitive in some settings.

**Source:** https://arxiv.org/abs/2605.18421

### YiSang benchmark plan

Build a small internal suite before adopting a large benchmark:

1. 10 static/dynamic knowledge questions.
2. 10 workflow/gotcha questions.
3. 10 cross-session execution questions.
4. Run with memory disabled, session-only, retrieval memory, and retrieval + procedural memory.
5. Record accuracy, evidence correctness, latency, context tokens, and memory write count.

---

## 10. Embedded vector search is an optimization layer, not memory itself

**Status:** EXPERIMENT

The internal `AI-Tech-Archive` already identified `sqlite-vector`/TurboQuant as a compact local vector-search candidate. This fits YiSang only as a secondary retrieval index.

### Rule

```text
Memory record != embedding row
```

Embeddings, quantized vectors, FTS indexes, and graph indexes should be rebuildable derivatives of authoritative memory records.

### Benchmark dimensions

For 1k / 10k / 100k memory records measure:

- recall@10
- p50 / p95 search latency
- resident memory
- DB size
- index build time
- rebuild correctness
- exact lexical fallback quality

**Archive reference:** `AI-Tech-Archive/research/2026-09-15-cross-project-tech-radar-20-v6.md`

---

# Recommended implementation order

## P0 — architectural hardening

1. Split local `RunContext` from model-visible `ContextPack`.
2. Add context-budget accounting.
3. Add metadata-only E.G.O discovery + lazy activation.
4. Build a 30-case memory/experience benchmark harness.

## P1 — durable state

5. Implement persistent SQLite `MemoryPort` backend.
6. Add provenance fields and evidence pointers.
7. Add `SessionPort` for non-authoritative conversation history.
8. Add deterministic run journal/checkpoint format.

## P2 — capability interoperability

9. Add Agent Skills import/export adapter for E.G.O.
10. Add an MCP adapter compatible with the 2026-07-28 protocol model.
11. Experiment with long-running `CapabilityExecution` handles and MCP Tasks mapping.

## P3 — advanced retrieval

12. Add rebuildable vector index.
13. Add optional timeline projection.
14. Add optional entity/event projection.
15. Compare projection combinations using the benchmark harness instead of assuming a universal winner.

---

# Non-goals

Do not:

- make OpenAI Agents SDK, LangGraph, MCP, or Agent Skills a hard dependency of YiSang Core;
- let session history bypass memory governance;
- let an embedding/vector database become the source of truth;
- allow an engine backend to mutate identity or durable memory directly;
- store secrets in LLM-visible context;
- adopt benchmark leaderboard claims without reproducing them on YiSang workloads.

---

# Source archive used

Internal source material:

- `stickleetoto/AI-Tech-Archive`
- `research/2026-09-15-cross-project-tech-radar-20-v6.md`

External references reviewed 2026-09-17:

- Agent Skills specification — https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx
- OpenAI Agents SDK context — https://openai.github.io/openai-agents-python/context/
- OpenAI Agents SDK sessions — https://openai.github.io/openai-agents-python/sessions/
- MCP 2026-07-28 release — https://blog.modelcontextprotocol.io/posts/2026-07-28/
- MCP Tasks draft — https://tasks.extensions.modelcontextprotocol.io/specification/draft/tasks
- LangGraph v1 — https://docs.langchain.com/oss/python/releases/langgraph-v1
- LongMemEval-V2 — https://arxiv.org/abs/2605.12493
- EvoMemBench — https://arxiv.org/abs/2605.18421
- Agent Zero Memory — https://arxiv.org/abs/2608.29606
