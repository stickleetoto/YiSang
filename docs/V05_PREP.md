# YiSang v0.5 Identity Continuity — Preparation

Status: **snapshot + restore-planning foundation implemented / restore application pending**

v0.5 must prove that changing the reasoning engine changes reasoning quality but
does not create a new YiSang identity.

## Foundation now present

### Versioned identity snapshot

`IdentitySnapshot` captures engine-independent persistent state:

- identity charter
- active project
- current goal / active goals
- engine-independent tags
- authoritative memory digest + schema version
- E.G.O registry digest
- optional future Library reference
- policy version
- runtime compatibility version
- explicit migration history
- snapshot schema version

`active_engine` is deliberately excluded from authoritative snapshot state.

### Integrity

Snapshots are written as a checksummed envelope:

~~~text
snapshot_schema_version
payload_sha256
payload
~~~

Tampering with the payload is detected before the snapshot is accepted.

### Continuity fingerprint

`continuity_fingerprint()` hashes persistent agent identity/state while
excluding capture-instance data such as:

- snapshot id
- snapshot timestamp
- replaceable engine selection
- runtime build/version hint

This gives the v0.5 engine-swap suite a stable comparison target.

### Runtime reference validation

`validate_snapshot_against_runtime()` checks:

- agent id
- authoritative memory digest
- E.G.O registry digest
- engine-independent state

An engine swap by itself must not fail this check. Persistent state drift must.

## Restore-planning foundation now present

- explicit SnapshotMigrationRegistry
- unambiguous migration-path planning
- pure migration transforms with MigrationRecord evidence
- RestorePlan before mutation
- target-engine registration check
- memory / E.G.O / engine-independent-state drift detection
- pure IdentityCharter reconstruction
- pure AgentState reconstruction with the replacement engine supplied externally

## Next v0.5 implementation steps

1. validate concrete referenced store locations before applying restore
2. add atomic/staged restore application
3. persist restore evidence / restore report
4. reject partial restore after any failed dependency validation
5. add Library reference validation when Roland exists
6. extend the engine-swap suite to two real local engine families
7. add corruption / partial-store / stale-schema restore cases
8. build the release-level continuity report

## Restore rule

Restore must follow:

~~~text
load
 -> verify checksum
 -> verify snapshot schema
 -> verify referenced stores
 -> plan migrations
 -> reject contradictions
 -> apply restore
 -> validate restored runtime
 -> record restore evidence
~~~

A snapshot is not trusted merely because it parses as JSON.
