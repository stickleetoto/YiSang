# YiSang v0.5 Identity Continuity — Preparation

Status: **implementation complete / real two-engine validation pending**. See `docs/V05_CLOSEOUT.md`.

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

## Portable continuity bundle now present

A v0.5 continuity bundle packages:

- the checksummed identity snapshot payload
- the authoritative memory archive
- the E.G.O manifest set

The bundle has its own envelope checksum and then independently verifies that
the embedded memory and E.G.O artifacts match the snapshot references. A valid
envelope therefore cannot silently substitute a different persistent store.

A fresh runtime with the same YiSang agent id can be rehydrated from the bundle
onto a different registered reasoning engine through the staged restore path.

## Continuity evaluation harness now present

The harness performs the repeatable sequence:

~~~text
source runtime
 -> build portable continuity bundle
 -> create/receive a fresh target runtime
 -> staged restore onto target engine
 -> compare identity / goal / state / memory / E.G.O digests
 -> compare continuity fingerprint
 -> issue a post-restore probe request
 -> verify the replacement engine is actually used
 -> verify expected durable memory and E.G.O capability are still reachable
 -> record restore + probe latency
~~~

Multiple target engines can be collected into one JSON continuity report. Unit
fixtures currently use deterministic EchoEngine replacements only; this does
not satisfy the real two-engine exit criterion.

## Live two-engine runner now present

`yisang-eval-continuity` accepts two OpenAI-compatible model endpoints/model
selections and exercises both the source and replacement engine around the
continuity-bundle restore boundary. Repeated runs emit mean/p95 restore and
probe latency alongside continuity invariants.

See `docs/EVAL_CONTINUITY_V05.md`.

## Closeout hardening now present

- partial continuity-bundle rejection
- contradictory memory schema/reference rejection
- reference-kind validation
- duplicate E.G.O id rejection
- checksummed RestoreReport persistence and tamper detection
- saved continuity-report loader
- explicit source/target model + engine-family evidence
- v0.5 closeout checker with minimum-repeat and distinct-family gates

See `docs/V05_CLOSEOUT.md`.

## Remaining validation work

1. run the deferred full repository tests
2. run the v0.4 memory benchmark/closeout checks
3. run the live continuity suite against at least two real local engine families
4. pass `yisang-eval-continuity-check` on the saved report
5. only then mark v0.5 validated

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
