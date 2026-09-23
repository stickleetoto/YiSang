# E.G.O v2 Capability System

## Goal

E.G.O v2 upgrades YiSang E.G.O from a conditional prompt manifest into a
versioned capability package with progressive disclosure, explicit contracts,
risk metadata, evaluation assets, and a path toward governed installation.

The v1 runtime remains supported. E.G.O v2 is additive.

## External research basis

### Agent Skills / progressive disclosure

Anthropic's Agent Skills design uses a directory-based skill package and loads
small discovery metadata first, then the full skill content only when relevant.
YiSang adopts the same high-level principle for E.G.O package discovery while
keeping its own manifest and governance model.

Sources:
- https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills

### A2A AgentSkill discovery shape

A2A 1.0 defines AgentSkill discovery metadata including id, name, description,
tags, and examples. E.G.O v2 keeps a compatible exportable subset so YiSang may
later advertise capabilities without exposing internal memory or implementation.

Sources:
- https://a2a-protocol.org/dev/specification/

### JSON Schema contracts

JSON Schema's current published dialect is Draft 2020-12. E.G.O v2 package
input/output schema files may declare this dialect. The foundation loader
parses and preserves these schemas; full runtime instance validation is a later
slice.

Sources:
- https://json-schema.org/specification
- https://json-schema.org/draft/2020-12/

### MCP-style risk vocabulary

MCP tool annotations use read-only, destructive, idempotent, and open-world
hints. The MCP guidance explicitly treats these as hints rather than trusted
authorization facts. E.G.O v2 mirrors that vocabulary in EgoRiskHints, and
does not use the hints as an authorization engine.

Sources:
- https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/

### Cedar authorization direction

Cedar models authorization requests around principal, action, resource, and
request context, with policy separate from application code. YiSang does not
embed Cedar in this foundation slice, but the future E.G.O permission engine
should use a similarly explicit authorization boundary.

Sources:
- https://docs.cedarpolicy.com/
- https://docs.cedarpolicy.com/policies/syntax-policy.html

### Artifact distribution/signing direction

OCI manifests support content-addressed artifacts and artifactType metadata.
Sigstore/Cosign can sign and verify artifacts/blobs. E.G.O v2 foundation starts
with an internal SHA-256 package digest; OCI packaging and Sigstore verification
are later distribution layers.

Sources:
- https://specs.opencontainers.org/image-spec/manifest/
- https://docs.sigstore.dev/quickstart/quickstart-cosign/

## YiSang-specific architecture

~~~text
E.G.O package directory
        |
        +-- manifest.json       discovery metadata
        +-- SKILL.md           detailed instructions
        +-- schemas/           input/output contracts
        +-- references/        optional support knowledge
        +-- scripts/           future executable assets
        +-- evals/             capability validation cases
        |
        v
discover_ego_packages()
        |
        | metadata only
        v
VersionedEgoRegistry
        |
        v
HybridCapabilityRouter
        |
        | select id + version
        v
activate()
        |
        | full package load + digest
        v
Context / Tool / Policy integration
~~~

## Why manifest.json first

The existing YiSang v1 E.G.O format already uses manifest.json and the project
currently has zero runtime dependencies. The v2 executable foundation therefore
keeps JSON to preserve dependency and migration simplicity. A YAML presentation
format can be added later without changing the in-memory EgoManifest v2 model.

## E.G.O package schema v2

Example:

~~~json
{
  "schema_version": 2,
  "ego_id": "ego.python.debug",
  "version": "1.2.0",
  "name": "Python Debugger",
  "description": "Diagnose and repair Python pytest failures.",
  "provides": ["python.debug", "python.test.repair"],
  "keywords": ["python", "pytest"],
  "tags": ["debugging", "testing"],
  "examples": ["pytest is failing", "fix this Python traceback"],
  "requires": ["filesystem.read"],
  "conflicts": [],
  "permissions": {
    "filesystem.read": true,
    "filesystem.write": "workspace"
  },
  "risk": {
    "read_only": false,
    "destructive": false,
    "idempotent": false,
    "open_world": false
  },
  "runtime": {"type": "native"},
  "instructions_file": "SKILL.md",
  "input_schema_file": "schemas/input.json",
  "output_schema_file": "schemas/output.json",
  "resources": ["references/pytest.md"],
  "evals": ["evals/basic.json"]
}
~~~

## Foundation invariants

1. Legacy v1 manifests continue to load as before.
2. Discovery reads manifest metadata but does not load SKILL.md or schemas.
3. Only an activated package loads detailed instructions and contracts.
4. Package file references must be relative and may not escape package root.
5. Full package loading emits a SHA-256 digest over the canonical manifest and
   referenced files.
6. Package versions use semantic major.minor.patch form.
7. Risk fields are hints, not authorization decisions.
8. A2A export exposes discovery metadata only.
9. V2 capability metadata participates in YiSang E.G.O registry continuity
   digests.
10. The hybrid router can work entirely on metadata summaries.

## Hybrid routing foundation

The first hybrid router remains deterministic and embedding-free. It combines:

- exact keyword phrase hits;
- tag token overlap;
- provided capability token overlap;
- description token overlap;
- example overlap;
- explicit required capability filters;
- optional bounded historical success priors.

Embedding retrieval can be added later behind the same rank/route contract.

## Roadmap

### Phase 1 - Foundation (this branch)
- EgoManifest v2
- progressive package discovery/load
- input/output schema loading
- safe package paths
- SHA-256 package digest
- semantic version registry
- A2A AgentSkill export
- deterministic hybrid router
- continuity digest binding

### Phase 2 - Governed installation
- durable EgoPort
- active/disabled/superseded package state
- PromotionArtifact -> E.G.O package apply
- rollback and supersession
- installation receipts

### Phase 3 - Authorization
- typed permission requests
- principal/action/resource/context authorization boundary
- policy engine adapter (Cedar/OPA candidate)
- risk hints remain advisory only

### Phase 4 - Execution runtimes
- prompt-only package
- native trusted package
- WASM/WASI sandbox package
- remote/A2A package
- runtime-specific resource limits

### Phase 5 - Distribution
- OCI artifact packaging
- immutable digest references
- Sigstore/Cosign verification
- trusted signer policy

### Phase 6 - Learned routing and adapters
- embeddings/RRF for discovery
- E.G.O telemetry and eval feedback
- learned routing weights
- optional signed LoRA adapter runtime


## Durable E.G.O installation and promotion bridge

The next v2 layer adds an authoritative EgoPort separate from the legacy
file-based registry.

~~~text
PromotionArtifact
      |
      | explicit approved apply
      v
DurableEgoApplyAdapter
      |
      v
EgoManifest v2 (prompt runtime)
      |
      v
EgoPort
  +-- active
  +-- disabled
  +-- superseded
      |
      v
DurableEgoRegistryView
      |
      v
HybridCapabilityRouter / YiSangRuntime
~~~

Rules:

- promotion never mutates an E.G.O store without an explicit PromotionApplyRequest;
- a promoted artifact becomes a new immutable semantic version;
- integer promotion versions map deterministically to 0.0.N;
- installing a newer version supersedes the currently active version;
- rollback reactivates an already installed version instead of rewriting it;
- only active E.G.O packages are exposed through DurableEgoRegistryView;
- every promoted package carries a SHA-256 digest bound to promotion provenance;
- generated promoted E.G.O packages use prompt runtime only in this phase;
- risk hints remain conservative and do not grant execution permission.


## Adaptive telemetry routing

E.G.O routing may consume historical outcome telemetry, but only as a bounded
secondary signal.

Recorded event kinds:

- runtime_use: verification result, action failure count, latency;
- replay_health: later deterministic replay pass/fail.

Adaptive scoring rules:

- fewer than 3 observations: zero routing adjustment;
- runtime outcomes use weight 1;
- replay-health outcomes use weight 2 by default;
- observations decay with a configurable half-life;
- neutral Bayesian smoothing prevents extreme early rates;
- adjustment is signed and capped at +/-0.35 by default;
- semantic metadata relevance remains the dominant routing signal.

The telemetry scorer does not disable packages. Lifecycle invalidation remains a
separate reviewed process.

~~~powershell
yisang-ego-adaptive-smoke
~~~
