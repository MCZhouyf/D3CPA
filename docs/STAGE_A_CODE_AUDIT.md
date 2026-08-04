# Stage A code audit

## Scope and method

- Audited checkout: `IPM-claude` / `3464478`.
- Static search used the Stage A required expressions over `MP5_agent/agent` and `MP5_agent/dc3pa`; historical date-stamped agent copies and commented examples were classified separately and are not the active import path.
- Option B process environment is pinned to `DC3PA_LEGACY_TASK_HACKS=0` and `DC3PA_CONTROLLER_BOUNDED_RESOURCE_FALLBACK=1`.

## Required three paths

| Path | Evidence | Layer | Option B result |
| --- | --- | --- | --- |
| `Planner._inject_prerequisite_steps` | `MP5_agent/agent/planner.py:75-100`; immediate `if not legacy_task_hacks_enabled(): return workflow_dict` at 76-77 | Planning | OFF: `LEGACY_TASK_HACKS=0` returns the LLM workflow before the wooden-pickaxe insertion at 85-98. |
| `Evaluator._fixed_workflow_for_task` | `MP5_agent/agent/run_agent.py:118-174`; gate at 119-120 before redstone test at 121 | Planning | OFF: `LEGACY_TASK_HACKS=0` returns `None`; the fixed redstone workflow is unreachable. |
| Deep-mining resource/craft fallback | `MP5_agent/agent/controller.py:37-43`, `224-246`, `257-311`, `313-386` | Execution | ON: target must be `diamond`, `redstone`, or `gold`, and the gate accepts either legacy mode or `BOUNDED_RESOURCE_FALLBACK=1`; thus Option B retains the bounded low-level substitute with legacy planner paths off. |

This split is substantive: the two planning paths replace the prerequisite-detection mechanism claimed in the paper, whereas the remaining controller code is a disclosed low-level execution substitute for the unavailable MP5 interface.

## Other task-name and inventory-write references

| Evidence | Classification | Finding |
| --- | --- | --- |
| `agent/controller.py:41,46,97-123,133-245,257-386,538-543` | Execution layer | Active deep-mining gate, inventory replacement primitive, and bounded resource/craft/log fallbacks. All direct writes route through `_set_inventory_from_memory` at 97-123. They remain ON under Option B and must be logged. |
| `agent/controller.py:741` | Execution telemetry | Records the task in an execution event; no task-specific branch. |
| `agent/controller.py:1304-1311` | Generic execution | Goal check compares the requested task/quantity with inventory; not task-specialized. |
| `agent/run_agent.py:202` | Generic execution | Episode-start `set_inventory([])` reset. It is not a substitute and Stage A analysis excludes its zero grant. |
| `agent/run_agent.py:236,303,324` and `agent/work_memory.py:144,296-309` | Generic / memory | Task naming and workflow-memory lookup/write/reset. This is the source of the A5 order-risk, not a planning shortcut. |
| `dc3pa/integration/legacy.py:144-175` | Generic adapter | Converts a task name for an optional legacy memory sink; no task-specific plan or inventory write. |
| `dc3pa/baseline/audit.py:23-52`, `dc3pa/baseline/patcher.py:64-124` | Tooling, non-runtime | Static audit/patch tooling that recognizes or installs the gates; it is not invoked by the Stage6 runtime. |
| `agent/2024*/*` and commented `structured_actions.py` examples | Historical / commented | Old snapshots and comments, not the active modules imported by `run_agent.py`; reported to avoid hiding search hits. |

No additional active planning-layer task-name branch was found beyond the two required gated paths.

## ControllerAdapter mode symmetry

`MP5_agent/dc3pa/integration/runtime.py:100-131` receives one `ControllerAdapter` as `controller` and stores it once in `self.controller` at line 121. The only execution call is `self.controller.execute(...)` at lines 739-743, outside the runtime-mode plan-selection branches. `MP5_agent/dc3pa/integration/factory.py:104-156` constructs `LegacyControllerAdapter(legacy_controller, ...)` once for every mode. This proves code-level controller identity across `mp5_legacy`, `reasoning_only`, and `dc3pa`; empirical call-rate symmetry remains an A4 measurement.

## Reliability coefficient reconciliation

`MP5_agent/dc3pa/reliability/config.py:28-40` sets `memory_weight_growth=0.02`. Existing alignment documentation states that the manuscript reports only visual-fusion `alpha=0.7`, not a distinct memory-growth alpha: `docs/PAPER_ALIGNMENT_STAGE3_5.md:29` and `docs/BUILD_REPORT_STAGE3_5.zh-CN.md:35`. Therefore `0.02` is an engineering default, not a paper-reproduced alpha. Stage F must correct any prose that calls it an original paper hyperparameter.

## Formal-task binding

The Stage A formal registry is `/external/dc3pa/task_assets_schema/final_task_catalog.csv`, with 50 entries (10 per tier). Its immutable hash and all task-to-JSON mappings are frozen in `configs/stage_a_formal_taskset_manifest.json`. The external mapping manifest requires runtime registry validation for every candidate target; static scope below is not empirical evidence.
