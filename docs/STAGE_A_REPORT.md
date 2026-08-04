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

## Table A — actual substitute scope

| Measure | Current value |
| --- | --- |
| `raw_write_records` | pending pilot |
| `substitute_write_records` | pending pilot |
| Actual affected tasks / static hypothesis | pending / 2 of 50 (static only) |
| Grants by task/tier | pending pilot |
| `calls_by_function` attribution | pending pilot |

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
