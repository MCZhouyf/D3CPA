# Stage A report (Option B)

## Status: runtime evidence pending — do not use as a completed experiment report

The Stage A additive tooling, static audit, formal 50-task binding, and frozen Option-B configuration are complete. Formal execution tables remain pending because readonly Stage6 runs require an approved frozen memory snapshot manifest that is absent from this checkout. No synthetic snapshot, surrogate task set, prompt edit, or base-code edit was used.

## Completed

| Item | Result | Evidence |
| --- | --- | --- |
| Base code immutability | Pass | `git diff --stat -- MP5_agent/agent MP5_agent/dc3pa` is empty. |
| Prompt templates | Unchanged | No prompt file was edited. |
| Tool tests | Pass | `python -m pytest dc3pa_stage_a/test_stage_a.py -q`: 14 passed. |
| A0 static audit | Complete | `docs/STAGE_A_CODE_AUDIT.md`. |
| A1 frozen Option-B config | Complete | `configs/paper_run_config.json`, hash `81a3708d…7aa2`; mode-invariant non-mode hash `79209385…a510`. |
| Formal task binding | Complete | `/external/dc3pa/task_assets_schema/final_task_catalog.csv`, 50 tasks/5×10 tiers, frozen in `configs/stage_a_formal_taskset_manifest.json`. |
| A2 attachment path | Complete, not yet environment-executed | `dc3pa_stage_a/run_stage_a_episode.py` wraps `minedojo.make`, installs `InventoryWriteLogger`, asserts config before launch, and dry-run validates a formal JSON. |
| Offline analysis pipeline | Pass | Fixture-only analysis at `docs/evidence/stage_a/fixtures_analysis.json`; it is not formal evidence. |

## Table A — substitute scope

| Measure | Formal empirical value | Static preflight |
| --- | --- | --- |
| Formal tasks | pending episodes | 50 |
| Static gate-matched tasks | pending episodes | 2/50 (4%): `obtain diamond`, `mine redstone` |
| Per-task calls and grants | pending inventory-write log | not inferable statically |

See `docs/STAGE_A_STATIC_SCOPE.md`.

## Table B — per-mode symmetry

No formal episode has been run. The code-level precondition holds: all three modes use the single `ControllerAdapter` stored at `runtime.py:121` and invoked at `runtime.py:741-743`. The empirical calls-per-episode relative range, touched-episode fraction, grant composition, and ≤10% decision are **pending**.

## Table C — order invariance

No formal order experiment has been run. The code audit confirms the risk: `work_memory.py:144` reads historical workflow memory and `run_agent.py:303` writes it after success. The required acquire/evaluate_readonly forward/reverse comparison, plus same-order control if needed, is **pending**.

## Table D — dual-population success

No formal success-rate run has been performed. Full-population and substitute-free-subset rates are **pending**; no comparison claim may use them yet.

## Failures and unexpected findings

1. The supplied test command initially failed because `test_stage_a.py` used local-module imports while being invoked as a package. The additive test imports were corrected to package imports; the mandated command now passes 14 tests.
2. The supplied analyzer counted every inventory write. Because the real launcher resets inventory with `set_inventory([])`, that would have inflated substitute calls. The additive analyzer now filters real records to positive grants with a controller fallback in the caller chain, while retaining a conservative compatibility rule for historical stackless records. All 14 tests pass after the change.
3. The initial repository search did not expose the formal 50-task catalog. The user supplied the authoritative external path; it is now hash-bound. A different 100-entry acquisition schedule was deliberately not used.
4. No approved frozen Stage6 memory snapshot manifest was found. This is recorded in `docs/OPEN_DECISIONS.md`; execution is refused rather than silently using mutable or empty memory.

## Needed human decision

Provide/approve the frozen memory snapshot manifest and root that correspond to the 50-task acquisition data. Then run the additive launcher for: (i) logging-on/off A/B pairs, (ii) 10-task × 3-mode × 3-seed A3/A4 sample, and (iii) A5 forward/reverse memory protocol.
