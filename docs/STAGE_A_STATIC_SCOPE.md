# Stage A static substitute-scope hypothesis

This document is a static preflight hypothesis, **not** an empirical Table A
result. The formal 50-task catalog is bound by
`configs/stage_a_formal_taskset_manifest.json`.

`Controller._is_deep_mining_task` has the literal target gate `diamond`,
`redstone`, and `gold`; direct target matching yields two current formal tasks:
`obtain diamond` and `mine redstone` (2/50, 4%). `craft raw gold block` has the
target `raw gold block`, not `gold`.

That 2/50 figure must not be presented as the eventual affected-task count.
The v2 logger includes **every direct inventory write with a nonempty positive
`granted` delta**, including possible bootstrap writes. Empty grants (including
setup `set_inventory([])`) are excluded. The caller chain is retained only for
`calls_by_function` attribution; it never determines inclusion. Actual Table A
will report raw writes, positive-grant writes, affected tasks/tier, grants, and
attribution; an actual count over two will be highlighted rather than hidden.
