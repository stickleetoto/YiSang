# Pull Request Stack

> Updated: 2026-09-23

This document describes the current open YiSang PR dependency graph and the
recommended integration order.

## Dependency graph

~~~text
main
└─ #56 [v0.7 core] Experience promotion foundation
   ├─ #57 [optional/BIO] Memory provider adapter
   ├─ #58 [v0.7 replay] Ordered multi-step replay
   └─ #59 [E.G.O v2 1/4] Capability package foundation
       └─ #60 [E.G.O v2 2/4] Durable promotion lifecycle
           └─ #61 [E.G.O v2 3/4] Replay invalidation lifecycle guard
               └─ #62 [E.G.O v2 4/4] Adaptive telemetry routing
                   └─ #63 [chore] GitHub/docs cleanup
~~~

## Recommended integration sequence

1. Merge #56 into main.
2. Retarget #58 and #59 to main after #56 lands.
3. Merge #58.
4. Merge the E.G.O stack in order: #59 -> #60 -> #61 -> #62.
5. Merge #63 after #62.
6. Treat #57 separately; merge it after #56 when BIO interoperability is wanted.

#57 is intentionally not part of the E.G.O stack.

## Why #58 and #59 are siblings

Both were created from #56.

#58 extends deterministic replay.
#59 begins the E.G.O v2 line.

They do not depend on each other at branch ancestry level, even though future
integrated v0.7 behavior benefits from both.

## Retargeting rule

When a base PR is merged, update downstream PR bases rather than keeping merged
feature branches as long-term bases.

Expected progression:

~~~text
#56 merged
  -> #58 base = main
  -> #59 base = main

#59 merged
  -> #60 base = main

#60 merged
  -> #61 base = main

#61 merged
  -> #62 base = main

#62 merged
  -> #63 base = main
~~~

This keeps GitHub diffs understandable and avoids preserving obsolete stack
bases after their contents are already on main.

## Validation state

| PR | Area | Latest known validation |
| --- | --- | --- |
| #56 | Experience Promotion | 301 passed |
| #57 | Optional BIO provider | 320 passed |
| #58 | Ordered multi-step replay | 307 passed |
| #59 | E.G.O v2 foundation | 314 passed |
| #60 | Durable E.G.O lifecycle | 320 passed |
| #61 | Lifecycle guard | 326 passed |
| #62 | Adaptive routing | 336 passed + local Windows smoke suite |
| #63 | GitHub/docs cleanup | docs-only |

These counts are branch-specific snapshots, not cumulative release numbers.

## Branch cleanup policy

Do not delete a branch while its PR is open.

After a PR is merged and all downstream PRs are retargeted successfully:

1. confirm CI on the retargeted child PR;
2. confirm no other open PR uses the branch as a base;
3. delete the merged feature branch.

BIO remains a separate optional branch until its integration decision is made.
