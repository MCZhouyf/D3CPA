# Stage A report (Option B)

## Status: diagnostic infrastructure complete; external pilot pending authorization

Base code and prompts remain untouched. The Stage A v2 toolbox passed its
required offline suite (16 passed). The supplied v2 policy counts all positive
inventory grants, not a function allowlist. Six diagnostic episodes are planned
but not launched because their new task state would be transmitted to an
external relay and the explicit relay authorization currently on record is
limited to craft diamond.

| Guardrail | Status |
| --- | --- |
| `git diff --stat -- MP5_agent/agent MP5_agent/dc3pa` | Empty |
| Prompt modifications | None |
| Option B | `LEGACY_TASK_HACKS=0`; `BOUNDED_RESOURCE_FALLBACK=1` |
| Diagnostic memory | `disabled`; no long-term writes; required note frozen |
| Formal task source | External 50-task catalog, hash-bound manifest |
| Tool test | `python -m pytest dc3pa_stage_a/test_stage_a.py -q` → 16 passed |

## Planned diagnostic design

`configs/stage_a_diagnostic_batch_plan.json` defines:

| Group | Purpose | Episodes |
| --- | --- | ---: |
| Pilot | mine log + obtain diamond × three modes × one seed | 6 |
| G1 | static candidates plus conservative wooden-pick/cobblestone bootstrap chain × 3 modes × 6 seeds | 180 |
| G2 | two non-G1 tasks per tier × 3 modes × 2 seeds | 60 |
| G3 | logger on/off paired diagnostic: two G2 tasks × dc3pa × 3 seeds | 12 |
| Full diagnostic total | G1 + G2 + G3 | 252 |

The pilot will measure wall-clock time, success/attempt ceiling, trace-derived
LLM call counts, and any provider-exposed token usage. If the extrapolated full
diagnostic time exceeds eight hours, execution stops at that observation and a
human scale decision is requested; it is never scaled unilaterally.


## Pilot throughput result — partial and censored

The authorized six-episode pilot was launched serially on 2026-08-04. One
episode completed; the second was censored when the orchestration hard limit of
15 minutes terminated the batch. The remaining four were deliberately not
started. This is **not** a completed pilot, a success-rate result, a parity
result, or a paper result.

| Episode | Result | Wall time / calls | Scope observation |
| --- | --- | --- | --- |
| `mp5_legacy`, mine log, seed 31001 | success, 1 attempt | 80.1 s; 1 completed LLM call; token usage unavailable in the Stage6 trace | 2 raw writes; 1 positive grant, attributed to `_set_inventory_from_memory`: dirt×4, log×1, sapling×1 |
| `mp5_legacy`, obtain diamond, seed 31001 | censored before completion | exceeded the remaining 15-minute batch allowance; 3 completed and 1 timed-out LLM call | first controller attempt failed for missing wooden pickaxe; no terminal outcome |

The second record establishes that the full pilot did not complete within the
orchestrator window. Counting the two scheduled slots against the 900-second
window gives a conservative censored lower bound of 450 seconds/episode; the
252-episode plan is therefore at least **31.5 hours** under that bound, above
the eight-hour threshold. This is a throughput flag, not a performance claim.
No G1/G2/G3 expansion will be started without a human scale decision.

Table A's positive mine-log write is specifically evidence that the static 2/50
deep-mining hypothesis cannot be treated as empirical scope: a non-deep-mining
task already exercised a positive inventory write. It does not establish the
actual 50-task affected count.

## Table A — actual substitute scope

| Measure | Current value |
| --- | --- |
| `raw_write_records` | partial: 2 in the one completed mine-log episode |
| `substitute_write_records` | partial: 1 in the one completed mine-log episode |
| Actual affected tasks / static hypothesis | partial: 1 of 1 observed / 2 of 50 (static only) |
| Grants by task/tier | partial: basic mine log → dirt×4, log×1, sapling×1 |
| `calls_by_function` attribution | partial: `_set_inventory_from_memory`: 1 |

Any actual affected count above two will be conspicuous in the report.

## Table B — empirical mode symmetry

Pending pilot. The prespecified metric is calls per episode. Relative spread
≤10% is symmetric; >10% is asymmetric and requires escalation. Disabled-memory
symmetry does not replace a later frozen-readonly rerun.

## Table C — order invariance

Pending approved frozen snapshot. If a forward/reverse pair disagrees, run three
pairs and an off/off control before any interpretation.

## Table D — dual population

Pending actual logger data. It will show both all-task success and the subset
never touched by a positive substitute write.

## Acquisition schedule decision

The previous 100-entry schedule was inspected but not adopted. It is a separate
acquisition campaign with 25 distinct tasks, only 22 overlapping the formal 50,
and 100 seeds disjoint from this plan. See
`docs/STAGE_A_ACQUISITION_SCHEDULE.md`. It requires explicit human snapshot
approval.

## Required human decision

Authorize transmission of the six specified disabled-memory pilot task states to
the configured external relay. Separately, approve an exact current-registry
acquisition snapshot before any readonly memory evaluation.
