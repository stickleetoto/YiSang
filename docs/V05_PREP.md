# YiSang v0.5 Identity Continuity — Preparation

Status: **staged restore application implemented / real multi-engine validation pending**

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

## Staged restore application now present

- preflight RestorePlan before runtime mutation
- memory archive checksum and snapshot-reference validation
- E.G.O registry digest validation
- staging MemoryPort factory for authoritative-memory replacement
- staging E.G.O registry construction
- identity/state reconstruction with the replacement engine selected externally
- runtime component swap only after all required artifacts are staged
- rollback to original runtime references on post-apply validation failure
- post-restore continuity fingerprint validation
- persistent RestoreReport evidence

## Next v0.5 implementation steps

1. add a portable continuity bundle that packages snapshot + memory + E.G.O artifacts
2. validate concrete Library references when Roland exists
3. extend the engine-swap suite to two real local engine families
4. add stale-schema migration fixtures and partial/corrupt bundle cases
5. benchmark restore latency
6. build the release-level continuity report

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
