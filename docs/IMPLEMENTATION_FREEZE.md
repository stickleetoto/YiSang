# YiSang Implementation Freeze

This document defines the implementation freeze for the completed v0.4 and v0.5 development phases.

## Frozen baselines

### v0.4 Governed Memory

Frozen implementation branch:

`freeze/v0.4-implementation`

Baseline commit:

`d10409dff9701b3450d2b506e5ac98e186f951ee`

Status:

**implementation frozen / validated**

The branch represents the v0.4 implementation closeout before v0.5 development began.

### v0.5 Identity Continuity

Frozen implementation branch:

`freeze/v0.5-implementation`

Status:

**implementation frozen / live two-engine pass; saved-report closeout pending**

The branch is created from the freeze merge commit that records this policy and the v0.5 release-candidate metadata.

## Freeze rules

Frozen implementation branches are reference baselines.

Do not add normal feature work to them.

Allowed changes after freeze are limited to:

- validation fixes required to make the frozen implementation behave as designed
- security fixes
- data-corruption fixes
- migration/restore correctness fixes
- test corrections where the test itself is wrong
- documentation corrections that do not redefine architecture

New capabilities belong on `main` under the next roadmap phase.

## Validation does not rewrite history

A validation failure does not silently move the frozen baseline.

Use this flow:

~~~text
frozen implementation
        |
        v
validation
        |
   pass | fail
        |   |
        |   +--> fix on main / hotfix branch
        |         -> revalidate
        |         -> explicitly create a new freeze baseline if required
        |
        +--> mark validated
~~~

## Version policy

The main package version after this freeze is `0.5.0rc1`.

`rc1` means:

- v0.4/v0.5 implementation surfaces are frozen
- integrated validation is not yet complete
- real two-engine continuity evidence is still required
- the version must not be described as a validated v0.5 release yet

After the deferred validation pass succeeds, a later commit may promote the version to `0.5.0`.

## Required validation before v0.5 final

1. install the frozen candidate
2. run the full pytest suite
3. run the v0.4 memory benchmark
4. run the v0.4 memory audit against a representative SQLite store
5. run live v0.5 continuity across two different local engine families
6. run the saved-report closeout checker
7. record the resulting evidence
8. only then promote from `0.5.0rc1` to `0.5.0`

## Development after freeze

Normal feature development resumes on `main`.

The next feature phase is v0.6 Roland, but roadmap implementation should begin only after the v0.4/v0.5 deferred validation pass has either:

- passed, or
- produced explicit validation-fix work with the frozen baselines retained for comparison.
