# Current State

> Updated: 2026-09-23

YiSang is currently on the **v0.7 development line**.

The last fully closed release remains **v0.6.0 — Roland Library validated**.
Current development extends v0.7 Experience Promotion into ordered replay and
E.G.O v2 capability lifecycle work.

## Validated release baseline

- v0.4 Governed Memory — validated
- v0.5 Identity Continuity — validated
- v0.6 Roland Library — validated

## Active v0.7 development

### Experience Promotion

Root PR: **#56**

Implemented:

- normalized ExperienceEpisode capture
- verified ActionTrace capture
- replay manifests from verified tool evidence only
- deterministic replay
- generalization
- PromotionGate
- PromotionArtifact
- explicit approved durable apply

### Ordered Multi-Step Replay

PR: **#58**

Implemented:

- ordered trace-to-replay compilation
- one isolated shared workspace per replay case
- fail-fast execution
- exact tool-order validation
- per-step replay evidence

### E.G.O v2

PR stack: **#59 -> #60 -> #61 -> #62**

Implemented across the stack:

- versioned E.G.O v2 capability packages
- progressive metadata-first discovery
- selected-package full activation
- package SHA-256 binding
- A2A AgentSkill-shaped discovery export
- HybridCapabilityRouter
- durable EgoPort
- active / disabled / superseded lifecycle
- PromotionArtifact -> E.G.O package installation
- immutable version rollback
- replay-regression invalidation candidates
- append-only lifecycle audit
- runtime/replay telemetry
- bounded adaptive routing

Local Windows validation on the latest E.G.O stack:

~~~text
yisang-ego-v2-smoke         ready = true
yisang-ego-promotion-smoke  ready = true
yisang-ego-lifecycle-smoke  ready = true
yisang-ego-adaptive-smoke   ready = true

336 passed in 8.71s
~~~

GitHub CI also passes on Python 3.11 and 3.12.

### Optional BIO adapter

PR: **#57**

Status:

- optional MemoryProvider integration
- BIO repository is not modified
- fake/injected BIO smoke validation exists
- currently intentionally separate from the main E.G.O v2 line

BIO should remain optional. YiSang must continue to work without BIO.

## Open PR map

~~~text
main
└─ #56  v0.7 Experience Promotion foundation
   ├─ #57  optional BIO adapter
   ├─ #58  ordered multi-step replay
   └─ #59  E.G.O v2 capability package foundation
       └─ #60  durable E.G.O promotion lifecycle
           └─ #61  replay invalidation lifecycle guard
               └─ #62  adaptive telemetry routing
                   ├─ #63  GitHub/docs cleanup
                   └─ #64  permission policy engine
~~~

See `docs/PR_STACK.md` for merge/retarget guidance.

## Permission Policy Engine

PR: **#64**

Implemented on the current policy branch:

- principal / action / resource / context authorization requests
- deny-by-default policy evaluation
- explicit permit / forbid with forbid precedence
- resource-scoped policy checks
- tool-exposure preflight plus execution-time concrete-resource recheck
- E.G.O version as part of policy principal identity
- E.G.O risk hints as advisory context only

Repository CI baseline on the policy branch: **346 passed** on Python 3.11/3.12.

## Next engineering target

After the current stack is integrated and revalidated, extend policy coverage
to concrete side-effect capabilities such as filesystem.write, process.spawn,
network access, git mutation, and external tool execution, then evaluate whether
a Cedar/OPA adapter is useful without making either a core dependency.
