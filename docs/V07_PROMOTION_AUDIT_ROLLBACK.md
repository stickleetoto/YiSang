# YiSang v0.7 — Promotion Audit and Revocation

## Goal

Make learned Roland Usage Notes inspectable and reversible.

Experience promotion is no longer treated as a one-way mutation. Every promoted
or reinforced Usage Note can carry a mutation record that preserves provenance
and the exact before/after note state.

## Mutation model

~~~text
ExperienceCandidate
    |
    v
Promotion Gate
    |
    v
Library Usage Note mutation
    |
    +--> PromotionMutation
           operation
           actor
           reason
           before_note
           after_note
           evidence_ids
           verification_refs
           source_episode_ids
    |
    v
PromotionAuditPort
~~~

Operations:

- promote
- reinforce
- revoke

The default engine uses an in-memory audit store. Production callers can provide
SQLitePromotionAuditPort for restart-safe audit history.

## Revocation model

Revocation is conservative.

~~~text
candidate
  -> find complete audited promotion/reinforcement chain
  -> read current target Usage Note
  -> current note == latest audited after_note?
       no  -> conflict / stop
       yes -> restore state from first audited before_note
  -> candidate.status = revoked
  -> append revoke mutation
~~~

This means YiSang never blindly overwrites a Usage Note that changed after the
last audited learning mutation.

If the candidate originally created the Usage Note, revocation removes it.

If the candidate reinforced a pre-existing Usage Note, revocation restores the
exact pre-existing note instead of deleting it.

## Revoked candidates

A revoked candidate cannot silently learn itself again from later observations.

A later explicit review/re-enable mechanism can be added separately. Reusing the
normal automatic promotion path is intentionally blocked.

## Failure compensation

Promotion touches multiple stores:

- LibraryPort
- ExperiencePort
- PromotionAuditPort

There is not yet a cross-store database transaction. To reduce partial-write
risk, if the audit append fails after a Library mutation, the engine compensates
by restoring the previous Usage Note and prior candidate state before surfacing
the error.

Revocation performs the corresponding compensation if its audit append fails.

This is not a substitute for the v0.8 RunJournal/transaction work, but it keeps
v0.7 fail-closed under the currently supported store boundaries.

## Design influence

This slice follows the same broad principle used in BIO memory governance:
state changes need lifecycle state, provenance, and an audit trail; an evidence
record is not itself authoritative truth.

YiSang applies that principle specifically to learned capability changes.

## Next work

- durable cross-store transaction/journal coordination;
- explicit reviewer-controlled un-revoke path;
- anti-pattern warning promotion for validated failures;
- replay adapter implementations for pytest/build/static analysis;
- promotion benchmark and false-promotion metrics;
- v0.7 closeout gate.
