# YiSang v0.7 — Episode / Replay Validation

## Goal

Make experience promotion depend on reproducible evidence rather than a model or
caller merely asserting that an observation was verified.

This slice adds three boundaries:

~~~text
Runtime
  -> EpisodeRecord
  -> ReplayValidator
  -> ExperienceObservation(validation_method="replay")
  -> ExperiencePromotionEngine(require_replay=True)
  -> Roland Usage Note
~~~

## Episode contract

An EpisodeRecord is a compact authoritative record of one completed YiSang
request.

It contains:

- episode_id
- request_id
- goal
- outcome
- compact ordered steps
- verification references
- engine/project metadata
- deterministic SHA-256 fingerprint

Raw tool output is deliberately excluded from automatic Runtime episode capture.
The episode keeps action status, gate/failure summaries, completion evidence,
and final verifier evidence.

When EpisodePort is configured on YiSangRuntime, the Runtime records an episode
after verification and returns its episode_id. With no EpisodePort configured,
legacy behavior is unchanged.

Available stores:

- InMemoryEpisodePort
- SQLiteEpisodePort

SQLiteEpisodePort verifies the stored fingerprint and rejects re-use of one
episode_id for different content.

## Replay boundary

ReplayValidator never owns shell/build/test execution.

Instead:

~~~text
ReplayCheck
   |
   v
ReplayAdapter
   |
   +--> pytest adapter
   +--> build adapter
   +--> static-analysis adapter
   +--> custom deterministic verifier
   |
   v
ReplayCheckResult
   |
   v
ReplayValidator
~~~

This keeps side-effect execution outside the experience-promotion core.

Required replay checks fail closed when:

- the source episode was not successful;
- no checks exist;
- check IDs are duplicated;
- a required check fails/errors/skips;
- a required PASS has no evidence;
- an adapter returns a result for the wrong check ID;
- the adapter raises an exception.

A successful replay produces a deterministic verification reference:

~~~text
replay:<sha256>
~~~

The hash binds:

- the Episode fingerprint;
- replay check definitions;
- required/optional status;
- replay results;
- evidence references;
- result details.

## Replay -> Experience bridge

observation_from_replay() is the safe bridge.

It verifies that the replay result belongs to the exact Episode fingerprint and
then creates an ExperienceObservation with:

- verified=True
- validation_method="replay"
- source_episode_id
- replay verification_ref
- deterministic replay evidence_id

Reusing the same Episode/replay/lesson therefore creates the same evidence_id
and cannot inflate the promotion success count.

## Strict promotion mode

ExperiencePromotionEngine now supports:

~~~python
ExperiencePromotionEngine(
    ...,
    require_replay=True,
)
~~~

In strict mode, externally asserted/manual observations are rejected with
replay_verification_required.

The default remains false during v0.7 development to preserve compatibility
with existing callers. Autonomous promotion should use strict mode.

## Current safety properties

1. Raw Runtime output is not promoted directly.
2. Episode capture does not grant execution authority.
3. Replay execution remains behind an adapter boundary.
4. Required replay checks must provide evidence.
5. Replay evidence is bound to one exact Episode fingerprint.
6. Duplicate replay evidence cannot increase the success counter.
7. Existing failure/risk promotion gates still apply after replay validation.
8. Runtime episode persistence is opt-in and backward compatible.

## Next slice

The next useful v0.7 work is:

1. promotion mutation/audit records;
2. rollback/invalidation of promoted Usage Notes;
3. failure -> anti-pattern candidate -> replayed workaround -> durable warning;
4. concrete pytest/build replay adapters in the developer integration layer;
5. benchmark false-promotion rate and replay precision;
6. later, lesson-candidate generation from trajectories under a separate
   proposal/generation boundary.
