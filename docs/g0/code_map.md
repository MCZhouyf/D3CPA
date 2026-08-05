# G0 code map

Baseline: `success-finish` → `06a708e2dcfc6bb83d48e41b1475cf0581db15d5`.

## Formal execution path

`dc3pa_stage_a/run_stage_a_episode.py:main` validates a frozen entry in
`configs/stage_a_formal_taskset_manifest.json`, sets the two Stage-A seed
variables, and delegates to `MP5_agent/scripts_dc3pa/stage6_run_minecraft.py:main`.
The Stage-6 launcher imports `MP5_agent/agent/run_agent.py` dynamically, creates
`run_agent.Evaluator`, `Work_Memory`, `Planner`, `Reflexion`, and
`Controller`, then calls `dc3pa.integration.factory.build_stage6_runtime`.
`Stage6ClosedLoopRunner.run_task` in `dc3pa/integration/runtime.py` obtains a
`Plan`, and `LegacyControllerAdapter.execute` in
`dc3pa/integration/controller.py` delegates to
`agent.controller.Controller.check_and_execute_workflow`.

## Configuration and model resolution

Stage-A paper configuration is parsed by `dc3pa_stage_a/paper_config.py:load`.
Its `export_env` precedes the Stage-6 CLI. `stage6_run_minecraft.py:main` then
loads the JSON selected by `--config`, applies CLI mode/attempt-policy overrides,
and reads model endpoint/key/name from CLI arguments (with environment defaults at
argument-construction time). `dc3pa.integration.stage6_config.Stage6RuntimeConfig`
is the Stage-6 runtime configuration type. Older `dc3pa/config.py` is used by the
baseline launcher path rather than the Stage-A formal launcher.

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
- Legacy workflow memory: `agent/work_memory.py:Work_Memory` reads/writes
  `agent/memory/workflows_*.json`; its Stage-6 sink is
  `dc3pa/integration/legacy.py:LegacyWorkflowMemorySink`.
- Newer memory stores: `dc3pa/memory/` and `dc3pa/integration/runtime.py`.

## Environment, seed, and budgets

`agent/run_agent.py:Evaluator.__init__` creates MineDojo and reads
`DC3PA_WORLD_SEED`/`DC3PA_SIM_SEED`, with a random world-seed fallback in the
baseline. `dc3pa_stage_a/run_stage_a_episode.py:main` sets both variables from
its `--seed`. `random` and NumPy are seeded in `Evaluator.__init__`; Torch has no
active formal-run seed call. `Stage6RuntimeConfig.max_execution_attempts` is the
runner retry budget; `StepBudgetEnv` in the Stage-A launcher optionally bounds
environment steps.

## Formal task set

The source catalog is `/external/dc3pa/task_assets_schema/final_task_catalog.csv`.
The frozen repository manifest is `configs/stage_a_formal_taskset_manifest.json`;
each JSON task is external under
`/external/dc3pa/task_assets_schema/creative_task_jsons/`. Structured formal
specifications are under `/external/dc3pa/task_assets_schema/formal_task_specs/`.

## State writes and feature flags

The formal code path clears inventory during episode setup in
`scripts_dc3pa/stage6_run_minecraft.py` and has the delayed log write in
`agent/controller.py:Controller._set_inventory_from_memory`. Stage-A wraps
`set_inventory` with `dc3pa_stage_a/inventory_write_logger.py:InventoryWriteLogger`
for audit only. Existing flags are defined in `agent/dc3pa_feature_flags.py`,
`dc3pa/config.py:FeatureFlags`, and `dc3pa_stage_a/paper_config.py`.

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
