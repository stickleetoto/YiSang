# YiSang v0.5 Identity Continuity — Implementation Closeout

Status: **implementation complete / real two-engine validation pending**

This closeout records implementation coverage only. It does not claim that the
deferred repository test pass, v0.4 integrated memory validation, or the real
Llama/Qwen continuity run has already passed.

## Implemented

### Snapshot and integrity

- versioned `IdentitySnapshot`
- engine-independent identity/state payload
- active goal continuity
- authoritative-memory reference + digest
- E.G.O registry reference + digest
- optional Library reference slot
- policy/runtime compatibility fields
- explicit migration history
- checksummed snapshot envelope
- corruption detection
- engine-independent continuity fingerprint

### Restore planning and migrations

- explicit `SnapshotMigrationRegistry`
- no implicit schema coercion
- ambiguous/missing migration paths rejected
- target-engine registration preflight
- memory/E.G.O/state drift detection
- pure IdentityCharter reconstruction
- pure AgentState reconstruction with engine supplied externally

### Staged restore

- all required artifacts validated before runtime mutation
- authoritative memory restored in an empty staging MemoryPort
- memory digest rechecked after staging
- E.G.O registry staged and digest checked
- runtime component references swapped only after staging succeeds
- post-apply snapshot validation
- post-apply continuity fingerprint validation
- rollback to the original runtime references on failure

### Restore evidence

- `RestoreReport`
- source snapshot digest
- pre/post runtime snapshot ids
- post-restore memory digest
- post-restore E.G.O digest
- restore start/apply timestamps
- checksummed restore-report envelope
- report tamper detection
- report acceptance requires `continuity_preserved=true`

### Portable continuity bundle

The portable bundle contains:

- identity snapshot
- authoritative memory archive
- E.G.O manifest set

Hardening includes:

- independent bundle-envelope checksum
- memory archive internal checksum
- memory schema/reference consistency check
- memory reference kind validation
- E.G.O reference kind/schema validation
- E.G.O digest validation
- duplicate E.G.O id rejection
- missing/partial artifact rejection
- contradictory artifact rejection

### Continuity evaluation

`yisang-eval-continuity`:

- exercises the source reasoning engine before capture
- creates a portable continuity bundle
- restores into a fresh target runtime
- switches to the requested replacement engine
- verifies identity / goal / state / memory / E.G.O continuity
- verifies continuity fingerprint equality
- exercises the replacement engine
- verifies expected durable memory remains retrievable on both sides
- verifies expected E.G.O remains selectable on both sides
- records repeated restore/probe latency
- records source/target model and explicit engine-family evidence

`yisang-eval-continuity-check` validates a saved report for v0.5 closeout:

- all cases passed
- minimum repeat count
- source engine exercised
- target engine exercised
- continuity fingerprint preserved
- source and target model evidence present
- source and target engine-family labels present
- engine-family labels differ

## Exit-criteria mapping

| v0.5 exit criterion | Implementation status |
| --- | --- |
| engine swap does not create a new identity | implemented; real run pending |
| restart + restore resumes same goal/state | portable fresh-runtime restore implemented |
| schema migrations explicit/testable | implemented |
| snapshot corruption detected | implemented |
| continuity across two different engines | runner/checker implemented; real run pending |

## Deferred validation pass

First update the local checkout:

~~~powershell
cd "D:\Users\leejy\Downloads\project\포폴\YiSang"
git pull
python -m pip install -e ".[dev]"
pytest -q
~~~

Then run the v0.4 deferred checks:

~~~powershell
yisang-eval-memory --output ".\artifacts\memory-v04.json"
~~~

Then perform the real v0.5 engine-family run. Example shape:

~~~powershell
yisang-eval-continuity `
  --source-base-url http://127.0.0.1:11434/v1 `
  --source-model "<llama-family-model>" `
  --source-engine-id llama-source `
  --source-family llama `
  --target-base-url http://127.0.0.1:11434/v1 `
  --target-model "<qwen-family-model>" `
  --target-engine-id qwen-target `
  --target-family qwen `
  --repeats 5 `
  --output ".\artifacts\continuity-v05.json"
~~~

Finally:

~~~powershell
yisang-eval-continuity-check `
  --input ".\artifacts\continuity-v05.json" `
  --min-repeats 3
~~~

Only after that checker returns ready should v0.5 be marked validated.

## Gate before v0.6

Roland/v0.6 may be designed in parallel, but v0.5 should not be declared
validated until the saved real-engine continuity report passes the closeout
checker.
