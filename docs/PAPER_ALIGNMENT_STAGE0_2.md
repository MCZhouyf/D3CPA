# Paper alignment contract for Stages 0-2

This document is a narrow implementation contract derived from the supplied DC3PA manuscript. It is not a substitute for the paper and does not extend the method beyond Stages 0-2.

## Stage 0: experimental hygiene

The paper compares planning success, reactive replanning and planning time. Before implementing the proposed mechanisms, the inherited MP5 behavior must therefore be measurable and selectable. The Stage 0 overlay records the run configuration, code/environment provenance, seeds, feature flags, process output and metrics that can be recovered from the current runner.

Known task-specific planner/controller behavior is not silently deleted. It is gated for controlled comparisons and reported by a source audit. General controller recovery remains inherited and is not claimed to be cleanly separated yet.

## Stage 1: stable component boundary

The later Cognitive Control Planner needs a stable boundary between high-level planning and the inherited Controller. Stage 1 therefore defines typed representations for:

- task and agent state;
- plans, plan steps and actions;
- execution results and episode trace events;
- reasoning/evaluation/controller interfaces.

The legacy action names and required arguments are preserved. The reasoning-only shell must remain behaviorally pass-through at this stage.

## Stage 2: Multimodal Memory Module

The manuscript defines two complementary successful-experience memories:

1. **Learned Dependency Schema**: a graph whose nodes are items and whose edges are prerequisite relations.
2. **Scene Exemplars**: context-rich successful observations paired with textual scene/task descriptions.

The implementation contract is:

- start from an empty cold-start memory;
- promote evidence only from episodes explicitly recorded as successful;
- keep dependency and scene storage independently queryable;
- retain provenance linking learned evidence to a successful episode;
- extract only dependencies explicitly represented by an action (materials, platform or tool), not causal edges inferred merely from temporal adjacency;
- store scene image/text vectors through pluggable encoders;
- treat included histogram/hash encoders as deterministic test fallbacks, never as MineCLIP or paper-grade semantic encoders;
- reject non-finite vectors and safely skip incompatible vector dimensions at retrieval;
- make database writes atomic and remove newly copied image files when the transaction fails;
- do not fabricate scene exemplars when importing legacy workflow-only memory.

## Explicitly deferred

The following belong to Stage 3 or later and must not be smuggled into this overlay:

- knowledge/model/environment probabilities;
- reliability fusion or learned strategy weights;
- Evaluation Chain corrections;
- adaptive evaluation frequency or trigger thresholds;
- end-to-end Minecraft/ALFWorld claims.
