# Stage 0-2 implementation notes

## Deliberate boundaries

1. Existing MP5 planner/controller files are not replaced. A guarded patcher inserts only narrow controls and aborts on source drift.
2. Stage 1 introduces contracts before changing behavior. A legacy workflow can be round-tripped back to the controller shape.
3. Stage 2 learns only from successful episodes. Failed trajectories remain trace evidence but are not promoted to dependency or exemplar memory.
4. Dependency extraction is conservative: it learns explicit craft material/platform and action tool requirements. It does not infer causality from mere temporal order.
5. Scene vectors are stored as little-endian float32 with recorded dimensions. Retrieval skips incompatible dimensions rather than coercing them.

## Known limitations before Stage 3

- No Hybrid Probability Model, Evaluation Chain or Adaptive Trigger is included.
- The general controller recovery flag is recorded but not wired through every controller branch.
- The original code's environment construction, retry accounting and success checks still require a later integration pass.
- MineCLIP loading is intentionally not hard-coded. Inject a callable encoder around the repository's actual MineCLIP implementation after checking its checkpoint/API.
- The legacy repository contains direct `env.set_inventory` fallbacks. The audit reports them; Stage 0's narrow patch does not delete them. Turning off deep-mining hacks prevents the known task-specific path from activating, but a full controller provenance audit is still required before paper-grade experiments.
