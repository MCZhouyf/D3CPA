# DC3PA Stage 6 implementation notes

Stage 6 closes the planning–execution loop without replacing the legacy MP5
Controller. The runtime selects one of three explicit modes:

- `mp5_legacy`: legacy fixed-workflow hook plus legacy Planner;
- `reasoning_only`: legacy Planner through the Stage-1 `Plan` contract;
- `dc3pa`: Stage-5 adaptive cognitive-control planning before execution.

The selected plan is executed as one complete legacy workflow. Stage 6 does not
split it into single-step Controller calls because the current Controller contains
workflow-level navigation and recovery behavior. This preserves the existing low-level
execution boundary.

## Closed-loop sequence

1. Snapshot current inventory, task context, position and optional RGB observation.
2. Produce a plan using the selected mode.
3. In `dc3pa` mode, collect the complete `PlanningOutcome`, including reliability,
   evaluation and patch history.
4. Block unresolved plans by default. A reasoning-only fallback or unsafe execution
   requires an explicit policy.
5. Send the finalized plan to the legacy Controller adapter.
6. Independently check the task goal after Controller success.
7. On failure, record one reactive replan and pass structured feedback to Reflexion.
8. On verified success only, update legacy workflow memory and Stage-2 multimodal
   memory.

## Metric boundaries

The runtime keeps these counts separate:

- `pre_execution_revision_count`: patches produced by the Evaluation Chain;
- `evaluation_count`: detailed evaluation calls represented in the planning outcome;
- `reactive_replan_count`: a new planning attempt scheduled after Controller/goal
  failure;
- `planning_fallback_count`: explicit reasoning-only degradation;
- `pre_execution_block_count`: plans rejected before Controller execution;
- `controller_execution_count`: finalized workflows actually sent to the Controller.

This separation avoids reporting Evaluation-Chain corrections as failure-driven
replanning.

## Fail-closed behavior

- unresolved DC3PA plans are blocked by default;
- a mismatched plan task is rejected before execution;
- Controller and goal-check exceptions become structured failures unless configured
  to raise;
- failed or blocked runs never update successful memory;
- final-scene capture and memory persistence failures are traced and do not relabel a
  verified environment success under the default `trace` policy;
- raw RGB arrays, embeddings and secret-like values are not serialized in runtime
  traces.

## Minecraft entry point

`scripts_dc3pa/stage6_run_minecraft.py` lazily imports the existing `agent/run_agent.py`
classes. Therefore `--help` and offline tests do not require MineDojo, while a real run
still requires the repository's MineDojo/JDK/model setup.

Paper-grade `pE` requires both a real image encoder and a real text encoder supplied to
`MultimodalMemory`. The CLI accepts `module:attribute` encoder factories. Histogram and
hash encoders are available only behind `--development-encoders` and print an explicit
warning. They must not be described as MineCLIP or used to claim paper results.

`mp5_legacy` uses a cached observation rather than adding a no-op environment step and
disables Stage-2 multimodal-memory writes in the CLI. It remains an instrumented adapter
path, not a claim of bit-for-bit replay across all external dependency versions.
