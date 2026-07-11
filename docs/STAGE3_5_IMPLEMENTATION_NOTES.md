# Stage 3–5 implementation notes

## Package layout

- `dc3pa/reliability/`: three reliability strategies, fusion, weight policy, configuration and factory.
- `dc3pa/evaluation/`: structured evaluator contracts, JSON provider adapter and atomic plan editor.
- `dc3pa/trigger/`: fixed and adaptive stateful trigger sessions.
- `dc3pa/planner/cognitive_control.py`: fixed-`M=1` and adaptive cognitive-control planners.
- `scripts_dc3pa/stage3_hpm_demo.py`: offline HPM demonstration.
- `scripts_dc3pa/stage4_dual_chain_demo.py`: offline repair and forced revalidation demonstration.
- `scripts_dc3pa/stage5_trigger_demo.py`: offline interval transition demonstration.

## Provider boundaries

The overlay does not import a vendor SDK. Integrators supply:

- `ConfidenceProvider.confidence(ConfidenceRequest)` for `pL`;
- `EvaluationProvider.complete(prompt)` for the Evaluation Chain;
- Stage-2 image/text encoders through `MultimodalMemory` for `pE`.

This keeps Stage 3–5 deterministic under fake providers and independently testable without network access.

## Primary construction path

```python
hpm = build_hybrid_probability_model(memory, confidence_provider, hpm_config)
planner = AdaptiveCognitiveControlPlanner(
    reasoning_chain,
    hpm,
    evaluation_chain,
    trigger_config=trigger_config,
)
outcome = planner.plan_with_outcome(task, state, reliability_context)
```

`PlanningOutcome` preserves the initial and final plan, all reliability results, trigger observations, evaluation reports, atomic patch records and unresolved decisions.

## Safety and invariants

- All probability values are finite and within `[0,1]`; booleans are rejected.
- Memory counts and trigger intervals must be non-negative/positive integers as applicable.
- Model-provider failures in `unavailable` mode are not cached, allowing recovery from transient errors.
- The environment score returns unavailable rather than guessing when visual/text evidence is absent or dimension-incompatible.
- Evaluation reports are tied to exact plan ID and version.
- Reliability results are checked against exact plan ID, version, step index and step ID before they affect the trigger.
- Plan edits are atomic and reject duplicate step/edit IDs, unknown targets and deletion of the entire plan.
- A revised plan gets a new plan ID, increments its version and points to the previous plan as parent.
- Raw images and vectors are excluded from evaluation prompt metadata and planner traces; Stage 6 must still ensure that arbitrary `AgentState.metadata` is suitable for its selected provider.

## Stage-6 integration contract

Stage 6 should adapt the current MP5 runner rather than changing Stage 3–5 internals. It must provide:

1. an `AgentState` and `ReliabilityContext` from current MineDojo observations;
2. real confidence/evaluation providers;
3. the final `Plan` to the existing Controller adapter;
4. structured execution results;
5. successful-episode memory writeback only after verified task completion;
6. separate metrics for pre-execution revisions and failure-driven replanning.
