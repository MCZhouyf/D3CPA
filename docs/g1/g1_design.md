# G1 design

G1 is an append-only, non-invasive observability stage.  A step row is created
only for a Planner high-level action submitted to the Controller.  Controller
telemetry and raw events are retained separately; the logger does not modify a
plan, a controller input, an environment action, or a budget.

The core matrix has six author-selected tasks and two core slots (11001 and
11002).  The author subsequently approved successful later runs as replacements
for failed/unavailable original-slot runs.  `runs/g1/core_slot_substitutions.json`
maps every slot to its actual execution seed and immutable raw-event hash.
Consequently, `core_slot_seed` is a matrix identifier, while
`actual_execution_seed` is the factual Minecraft world seed.
