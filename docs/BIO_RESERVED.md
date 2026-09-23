# BIO Reserved Integration

> Status: PARKED / RESERVED
> Updated: 2026-09-23

BIO is intentionally not an active YiSang development axis right now.

## Reserved seam

YiSang keeps a provider-neutral memory boundary so BIO can be attached later:

~~~text
YiSang Runtime
  -> MemoryProvider
       +-- NativeMemoryProvider
       +-- BioMemoryProvider   [optional / parked]
~~~

Existing work lives on:

- PR #57
- branch `dev/bio-adapter-foundation`

## Rules while parked

1. Native memory remains the default.
2. YiSang startup must not require BIO.
3. BIO is not merged into YiSang core.
4. YiSang must not vendor or copy BIO implementation code.
5. The BIO repository is not modified from this integration line.
6. MemoryProvider remains stable enough to resume the adapter later.
7. No active v0.8 design may depend on BIO being available.

## Resume trigger

BIO work resumes only when there is a concrete validation goal, such as:

- native vs BIO resume-quality comparison;
- stale-memory/correction benchmark;
- cross-engine long-term continuity experiment;
- isolated live BioMemoryBridge validation.

Until then, the adapter is a reserved interoperability slot, not a dependency.
