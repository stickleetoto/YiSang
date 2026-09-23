# Pull Request Stack

> Updated: 2026-09-23

## Active integration graph

~~~text
main
└─ #56 [v0.7 core] Experience promotion foundation
   ├─ #57 [PARKED/BIO] Memory provider adapter
   ├─ #58 [v0.7 replay] Ordered multi-step replay
   └─ #59 [E.G.O v2 1/4] Capability package foundation
       └─ #60 [E.G.O v2 2/4] Durable promotion lifecycle
           └─ #61 [E.G.O v2 3/4] Replay invalidation lifecycle guard
               └─ #62 [E.G.O v2 4/4] Adaptive telemetry routing
                   └─ #64 [E.G.O v2 policy] Permission policy engine
                       └─ closeout/docs PR
~~~

## BIO

#57 is parked and is not part of the current integration sequence.

Keep the branch and adapter seam. Do not merge it until BIO work is resumed
explicitly.

## Recommended integration order

1. #56 -> main
2. retarget #58 and #59 to main
3. merge #58
4. merge #59 -> #60 -> #61 -> #62 in order
5. merge #64
6. merge the closeout/docs PR
7. leave #57 parked

After each parent merge, retarget the next child to main and re-run CI before
deleting the merged parent branch.

## Validation snapshots

| PR | Area | Latest known validation |
| --- | --- | --- |
| #56 | Experience Promotion | 301 passed |
| #57 | BIO adapter | 320 passed; PARKED |
| #58 | Ordered replay | 307 passed |
| #59 | E.G.O v2 foundation | 314 passed |
| #60 | Durable E.G.O lifecycle | 320 passed |
| #61 | Lifecycle guard | 326 passed |
| #62 | Adaptive routing | 336 passed + Windows smoke suite |
| #64 | Permission policy | 346 passed + Windows policy smoke |

These are branch-specific snapshots, not release-level cumulative guarantees.

## Superseded PR

#63 was an earlier docs-cleanup PR created before #64. The closeout/docs branch
replaces it and carries forward the useful repository-organization content plus
the final policy/BIO/next-axis state.

## Branch cleanup rule

Delete a merged feature branch only after:

1. its child PR has been retargeted successfully;
2. child CI passes against the new base;
3. no open PR still uses the branch as a base.
