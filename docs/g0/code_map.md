# G0 code map

Baseline: `success-finish` → `06a708e2dcfc6bb83d48e41b1475cf0581db15d5`.

## Formal execution path

`dc3pa_stage_a/run_stage_a_episode.py:main` validates a frozen entry in
`configs/stage_a_formal_taskset_manifest.json`, sets `EPISODE_SEED` (and legacy
aliases for external wrappers), and delegates to
`MP5_agent/scripts_dc3pa/stage6_run_minecraft.py:main`.
The Stage-6 launcher imports `MP5_agent/agent/run_agent.py` dynamically, creates
`run_agent.Evaluator`, `Work_Memory`, `Planner`, `Reflexion`, and
`Controller`, then calls `dc3pa.integration.factory.build_stage6_runtime`.
`Stage6ClosedLoopRunner.run_task` in `dc3pa/integration/runtime.py` obtains a
`Plan`, and `LegacyControllerAdapter.execute` in
`dc3pa/integration/controller.py` delegates to
`agent.controller.Controller.check_and_execute_workflow`.

## Configuration and model resolution

`configs/g0_runtime.json` is the credential-free G0 source for model endpoint,
model name, temperature, top-p, token/retry limits, `EPISODE_SEED`, action budgets,
and feature flags. `stage6_run_minecraft.py:_resolve_g0_runtime` resolves CLI,
environment, then that file, installs the resulting seed and disables legacy
workflow memory and controller recovery. It writes a credential-free resolved
record adjacent to the execution trace. `dc3pa.integration.stage6_config.Stage6RuntimeConfig`
receives the resolved replan budget; `StepBudgetEnv` enforces the resolved maximum
environment steps.

## Planner, evaluation, controller, and memory

- Planner: `agent/planner.py:Planner.get_workflow`, adapted by
  `dc3pa/planner/legacy_adapter.py:LegacyPlannerAdapter` and
  `dc3pa/integration/mp5_workflow.py:LegacyMP5ReasoningChain`.
- Evaluation chain: `dc3pa/evaluation/chain.py:StructuredEvaluationChain`, wired
  only for `dc3pa` mode in `dc3pa/integration/factory.py:build_stage6_runtime`.
- Controller: `agent/controller.py:Controller.check_and_execute_workflow`, called
  via `dc3pa/integration/controller.py:LegacyControllerAdapter.execute`.
- State provider: `dc3pa/integration/factory.py:build_legacy_state_provider` and
  `dc3pa/integration/state.py:LegacyMP5StateProvider`.
- Legacy workflow memory: `agent/work_memory.py:Work_Memory` contains the legacy
  `workflows_*.json` implementation, but the G0 launcher sets
  `MP5_DISABLE_MEMORY=1`, so the formal path neither reads nor writes it.
- Newer memory stores: `dc3pa/memory/` and `dc3pa/integration/runtime.py`.

## Environment, seed, and budgets

`agent/run_agent.py:Evaluator.__init__` requires `EPISODE_SEED`, uses it for both
MineDojo `world_seed` and simulator `seed`, and seeds Python `random` and NumPy.
There is no formal random-seed fallback. Torch has no active formal-run use or
seed call. `Stage6RuntimeConfig.max_execution_attempts` is resolved from the G0
replan budget; `scripts_dc3pa/stage6_run_minecraft.py:StepBudgetEnv` bounds every
environment step.

## Formal task set

The source catalog is `/external/dc3pa/task_assets_schema/final_task_catalog.csv`.
The frozen repository manifest is `configs/stage_a_formal_taskset_manifest.json`;
each JSON task is external under
`/external/dc3pa/task_assets_schema/creative_task_jsons/`. Structured formal
specifications are under `/external/dc3pa/task_assets_schema/formal_task_specs/`.

## State writes and feature flags

The formal launcher clears the environment inventory during episode setup; this is
environment initialization, not policy compensation. The only policy-path direct
inventory write is the protected delayed log callback in
`agent/controller.py:Controller._set_inventory_from_memory`. Stage-A's
`InventoryWriteLogger` is audit-only. The effective final Controller methods are
audited by `scripts/g0_verify_formal_policy.py`; they only map declared actions to
low-level commands and return structured failures.

## Visual encoder and checkpoint path

`scripts_dc3pa/stage6_run_minecraft.py:_build_encoders` accepts dependency-injected
image/text encoder factories. It can use development histogram/hash encoders; no
formal MineCLIP checkpoint is resolved by the frozen Stage-A launcher. The active
encoder output dimension is supplied by the chosen plugin, not hard-coded in this
entry path.

## Protected log callback

The existing callback is in `agent/controller.py`:
`_gather_logs` invokes `_set_inventory_from_memory` after the fixed 100-step
window. Its Controller-local direct helpers are `_sync_memory`,
`_begin_log_callback_window`, `_log_callback_due`, and
`_complete_log_callback_window`. Exact AST hashes and protected call sites are in
`runs/g0/log_callback_protected_manifest.json`.
