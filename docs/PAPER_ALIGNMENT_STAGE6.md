# Stage 6 paper alignment and boundaries

The manuscript describes a closed loop in which the Reasoning Chain generates an
initial plan, the Adaptive Triggering Mechanism decides when the Evaluation Chain is
activated, the Hybrid Probability Model supplies reliability evidence, and the corrected
plan is then sent to the Controller. Stage 6 implements the integration boundary around
the Stage 3–5 modules; it does not change their formulas or trigger policy.

## Implemented alignment

- The finalized DC3PA plan, rather than the unverified initial plan, is sent to the
  legacy Controller.
- Knowledge/model/environment reliability and Evaluation-Chain output remain
  pre-execution evidence.
- Pre-execution revisions are measured separately from post-failure reactive replanning.
- Successful interaction experience is the only source of new dependency and scene
  memory.
- The Controller remains a high-level semantic-action executor, consistent with the
  manuscript's focus on decision-level regulation.
- The standard Stage 3–5 defaults remain available: visual weight `0.7`, trigger
  threshold `0.8`, initial interval `3`, and learned-strategy cap `0.4`.

## Deliberate implementation boundaries

- `memory_weight_growth=0.02` remains an engineering default because the manuscript
  does not provide a distinct numeric growth coefficient.
- The legacy Controller executes a complete workflow, so Stage 6 records initial and
  final successful scene exemplars rather than claiming per-action visual snapshots.
- No built-in adapter is labelled MineCLIP. A real encoder must be injected for a full
  environment-driven probability configuration.
- Offline tests use fake planners, Controllers and environments. They validate control
  flow and invariants, not Minecraft success, SR, RC, PT or paper-level reproduction.
- The standalone Minecraft entry point has not been exercised in this build environment
  because MineDojo, JDK, model credentials and encoder checkpoints are unavailable.
