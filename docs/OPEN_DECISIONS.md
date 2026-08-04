# Open decisions

## Stage A diagnostic execution

A snapshot-free diagnostic is now authorized by the work order only when
`memory_mode=disabled`, both long-term recording flags are false, and the
configuration carries the required diagnostic note. The frozen files are
`configs/stage_a_diagnostic_*.json`; they pin Option B and have an identical
non-mode hash. These runs measure substitute scope and per-mode symmetry only;
they are not paper configurations and cannot establish memory claims.

Execution additionally requires explicit authorization to send each new task
state to the external model relay. The current authorization on record covers
craft diamond only, so the six-episode Stage A pilot has not been launched.

## Formal readonly evaluation remains pending snapshot approval

`evaluate_readonly` still requires an approved frozen snapshot manifest/root.
No fake snapshot, substitute task set, or writable evaluation mode will be
used. `docs/STAGE_A_ACQUISITION_SCHEDULE.md` records the inspected 100-entry
candidate and why it needs a human approval before adoption.

## After a snapshot is approved

Run A5 forward/reverse order invariance and repeat A4 in readonly mode. Until
then both are documented as pending snapshot approval, not as completed
experiments.
