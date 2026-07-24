# Round 5.13E3 formal-50 smoke alignment

The successor Engineering Smoke retains nine assignments across all five
difficulty levels, but every task must resolve to an entry in the formal
50-task catalog. The historical E1R generator and artifacts remain unchanged.

The formal catalog has no combat goal. The successor therefore replaces the
find-only `creature` proxy with the Hard, experience-covered task `smelt iron
ingot`, represented by `agent/tasks/creative/iron_ingot.json`. Furnace
processing uses the legacy `craft` action contract. The smoke deliberately
omits `fight` rather than claiming unsupported semantic coverage.

The successor uses a new deterministic namespace so its task-seed assignments
cannot overlap the historical smoke namespace. It remains engineering-only,
fitting-ineligible, outcome-independent, and no-write. Freeze it explicitly
with `--formal-50-task-smoke`; the default freeze path still reproduces E1R.
