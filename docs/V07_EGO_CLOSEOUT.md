# v0.7 Experience + E.G.O v2 Closeout Candidate

> Date: 2026-09-23

This document freezes the current understanding of the completed v0.7/E.G.O
development axis before work begins on the next major subsystem.

This is a **closeout candidate**, not a declaration that the stack has already
been merged into main.

## Completed capability chain

~~~text
runtime work
  -> ExperienceEpisode
  -> ActionTrace
  -> deterministic replay
  -> ordered multi-step replay
  -> generalization
  -> PromotionGate
  -> PromotionArtifact
  -> approved E.G.O v2 installation
  -> runtime use
  -> telemetry
  -> adaptive routing
  -> post-install replay health
  -> invalidation candidate
  -> reviewed disable / rollback
  -> permission policy
~~~

## Core guarantees demonstrated

### Experience

- raw conversation text is not directly promoted;
- replay evidence is required;
- unverified replay manifests do not become executable replay specs;
- ordered replay preserves tool-step order;
- replay uses isolated workspaces and fail-fast behavior.

### E.G.O v2

- metadata can be discovered without loading full instructions;
- selected packages can be activated lazily;
- versions are explicit;
- package content is SHA-256 bound;
- promoted E.G.O installation is explicit and approved;
- older versions remain inspectable;
- rollback reactivates an immutable installed version.

### Lifecycle

- replay regression creates a pending invalidation candidate only;
- a replay failure does not automatically disable a capability;
- rejection leaves the capability active;
- approved invalidation disables only the still-active target version;
- lifecycle changes are auditable.

### Adaptive routing

- runtime and replay-health outcomes are recorded separately;
- fewer than the minimum sample count have no routing effect;
- feedback is version-scoped;
- old observations decay;
- routing adjustment is bounded;
- telemetry cannot make a semantically irrelevant E.G.O relevant.

### Permission policy

- model output does not create authority;
- legacy capability/permission checks remain in front of policy;
- configured policy mode is deny-by-default;
- explicit forbid overrides permit;
- concrete resource values are rechecked at execution time;
- risk hints are context only, never authorization.

## Validation evidence

Local Windows:

~~~text
E.G.O v2 smoke         PASS
Promotion smoke        PASS
Lifecycle smoke        PASS
Adaptive smoke         PASS
Policy smoke           PASS

346 passed in 8.87s
~~~

CI:

- Python 3.11 PASS
- Python 3.12 PASS
- policy branch full suite: 346 passed

## Deferred work

Not part of this closeout:

- live BIO integration
- broad side-effect tool enablement
- Cedar/OPA external policy adapter
- WASM E.G.O runtime
- OCI/Sigstore E.G.O distribution
- learned/embedding router
- autonomous privileged skill promotion
- long-horizon goal recovery

## Exit from this axis

The next axis must not require reopening E.G.O v2 design unless a concrete
v0.8 requirement exposes a defect.

Bug fixes and narrow policy/tool integration may continue, but new architectural
work should move to the v0.8 Goal / Recovery Runtime line.
