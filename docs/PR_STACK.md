# Pull Request Stack

> Updated: 2026-09-24

## Active stack

~~~text
main
└─ #56 [v0.7 core] Experience promotion
   ├─ #57 [PARKED/BIO] Memory provider adapter
   ├─ #58 [v0.7 replay] Ordered replay
   └─ #59 [E.G.O v2 1/4] Capability package
       └─ #60 [E.G.O v2 2/4] Durable lifecycle
           └─ #61 [E.G.O v2 3/4] Invalidation guard
               └─ #62 [E.G.O v2 4/4] Adaptive routing
                   └─ #64 [E.G.O policy] Permission policy
                       └─ #65 [closeout] v0.7/E.G.O freeze
                           └─ #66 [v0.8 1/4] Goal/recovery foundation
                               └─ #67 [v0.8 2/4] Restart controller
                                   └─ #68 [v0.8 3/4] Crash orchestration
                                       └─ #69 [v0.8 4/4] Real side effects
                                           └─ #70 [v0.9 1/3] Planner
                                               └─ #71 [v0.9 2/3] Recovery bridge
                                                   └─ #72 [v0.9 3/3] Replanning
~~~

## BIO

#57 stays open but parked. It is outside the active integration sequence.

## Recommended integration

Merge/retarget from the root downward. After each parent lands:

1. retarget its child to main;
2. run CI/local validation against the new base;
3. only then delete the merged parent branch.

Current active sequence after v0.7 closeout:

~~~text
#65
-> #66
-> #67
-> #68
-> #69
-> #70
-> #71
-> #72
~~~

## Validation state

v0.7/E.G.O through #64 has local Windows validation evidence.

The top-of-stack v0.8/v0.9 branch has completed Windows local validation:

~~~text
workspace recovery / planner / long-horizon / replan smokes: PASS
focused v0.8/v0.9: 23 passed in 0.41s
full repository: 369 passed in 9.13s
~~~

This validates the integrated stack through #72. Individual child PRs should
still be revalidated after each retarget/merge because their base commits will
change during stack integration.

## Superseded

#63 old docs cleanup is closed/superseded by #65 and later state documents.
