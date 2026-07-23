# Round 5.13E0 memory provenance

Round 5.13E0 validates full immutable MineCLIP payloads and reconstructs a
Scene Exemplar evidence manifest over an existing read-only Paper Memory V5
snapshot. The evidence release cannot rebuild memory, encode new vectors,
rerun deduplication, reassign owners, or mutate database rows.

The public repository contains only validation code, synthetic tests, and this
DRAFT inventory. Per-scene evidence, external paths, and frozen audit objects
remain outside Git.

An unresolved MineCLIP reference is classified as `M3` and blocks contract
supersession and smoke preparation. Aggregate scene counts are insufficient to
create a Scene Exemplar evidence release; all 144 retained rows require image,
embedding, source episode, action, subgoal, deduplication, and database-row
lineage.

The validator also requires the Paper Memory and frozen-memory releases to
bind the exact snapshot manifest, snapshot root, database, acquisition
manifest, checkpoint manifest, and release IDs. Matching aggregate counts or a
matching snapshot-root digest cannot substitute for a missing historical
manifest file.
