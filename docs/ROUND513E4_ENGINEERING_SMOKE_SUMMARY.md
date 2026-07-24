# Round 5.13 E4 Engineering Smoke Summary

## Scope and lineage

- Execution source: `50ab1dea09a37b6056dcb6b8671bfdbd55daf10c`
- Combined closeout: `f999fb1f35fdc2677f37ba2f6e04d501306b60813eaaebbc2441f53a2f952e97`
- Candidate B: `0dc2d2104e6b0cc7395716f0fb8a5a1e196c339d2c944ae51982ba945aef1b1f`
- Gamma: `gamma_cov=1.0`, `gamma_minus=-0.01040883`, `gamma_plus=0.00744657`
- Mode: CHRM-lite engineering smoke, one original Planner action per decision.
- Evaluation Chain calls before execution: `0`.
- Paper Memory V5 was mounted read-only. Memory and Acquisition writes were `0`.
- The nine frozen assignments ran in their original order. Numeric seeds remain redacted.

This report combines E4 R2 and its authorized E4 R3 continuation. The continuation did not rerun the six assignments already closed by R2. It only completed `diamond`, `redstone`, and `sapling` after the Provider retry budget stopped R2.

## Aggregate result

| Metric | Result |
|---|---:|
| Assignments closed | 9 / 9 |
| Accepted scientific records | 0 |
| Audit-only ambiguous records | 9 |
| Terminal task successes | 1 / 9 |
| Controller-reported action successes | 7 / 9 |
| Runtime Planner calls | 13 |
| Runtime Reflection calls | 8 |
| Evaluation calls | 0 |
| Controller executions | 9 |
| Provider preflight calls | 1 |
| Total LLM calls including preflight | 22 |
| Provider transport failures before Controller | 4 |
| Memory writes | 0 |

SnapshotGuard, credential scanning, source freeze checks, strict task order, and campaign-owned process cleanup all passed. No API key, endpoint, raw prompt, raw model response, numeric seed, generated database, image, or console log is included in this repository report.

## Per-task observations

| Order | Task | Original action | Confidence | Planner calls | Reflection calls | Controller success | Goal success | Scientific disposition |
|---:|---|---|---|---:|---:|---:|---:|---|
| 0 | log | `find:tree` | likely | 2 | 1 | true | false | audit-only ambiguous |
| 1 | cobblestone | `find:oak_log` | likely | 1 | 1 | true | false | audit-only ambiguous |
| 2 | iron ore | `find:iron_ore` | likely | 1 | 1 | false | false | audit-only ambiguous |
| 3 | crafting table | `find:tree` | likely | 1 | 1 | true | false | audit-only ambiguous |
| 4 | iron ingot | `find:tree` | likely | 1 | 1 | true | false | audit-only ambiguous |
| 5 | wooden pickaxe | `find:tree` | very_likely | 1 | 1 | true | false | audit-only ambiguous |
| 6 | diamond | `find:wood` | likely | 3 | 1 | true | false | audit-only ambiguous |
| 7 | redstone | `find:redstone_ore` | likely | 1 | 1 | false | false | audit-only ambiguous |
| 8 | sapling | `find:sapling` | likely | 2 | 0 | true | true | audit-only ambiguous |

The Planner counts include authorized pre-Controller technical attempts. Provider transport failures occurred once for `log`, twice for `diamond`, and once for `sapling`. No scientific success or scientific failure was retried.

## Main finding

The campaign infrastructure is operational, but the scientific labeling path is not yet informative for `find` actions. Every record had the same label reason:

`required_postcondition_evidence_missing`

For every task, the structured post-state had `target_visible=null`. Consequently, all nine actions became `ambiguous_unobservable`, including `sapling`, where the independent runtime goal check returned `goal_success=true`. This is direct evidence that the current action-postcondition instrumentation can discard an observed terminal success.

The distinction between Controller success and terminal goal success is also important. CHRM-lite evaluates one original action, not a complete multi-step solution. A prerequisite action such as `find:tree` can execute successfully while the terminal task `crafting table` remains incomplete. The next implementation must preserve action-level semantics instead of treating terminal task completion as the only action label.

## Memory and environment evidence

All nine decisions had the same high-level evidence shape:

- Hard action-schema check: `h=1`.
- Eligible soft knowledge rules: none, giving `k=0.0` and `u=0`.
- Compatible scene exemplar pool: empty.
- Positive scene coverage: `0.0`.
- Negative scene coverage: `1.0` with three selected incompatible exemplars.
- Online LLM calls inside retrieval: `0`.

This means the run verified deterministic read-only retrieval, but did not test useful bilateral evidence for these `find` action signatures. It would be premature to interpret the run as evidence for or against the frozen Gamma values or CHRM-lite calibration quality.

## Controller observations

Two actions exhausted bounded exploration naturally:

- `find:iron_ore` ended after 48 search iterations.
- `find:redstone_ore` ended after 41 search iterations.

These are scientific execution outcomes, not hangs or environment crashes. Other Controller calls reported action success, but only `sapling` satisfied the terminal task goal. No crafting-table reuse, furnace placement, cobblestone approach, or multi-step crafting behavior was exercised because all original Planner decisions were single `find` actions.

## Provider and process observations

The external Provider intermittently returned TPM rate-limit errors. The frozen retry rules behaved as intended:

- Failures before Controller execution produced no scientific record.
- Only explicitly authorized technical retries were used.
- No scientific outcome was retried.
- The final continuation completed all remaining assignments.

Provider instability increased cost and latency but did not contaminate accepted or audit-only records. It should be reported separately from Controller and labeling behavior.

## Recommended next implementation plan

1. Repair `find` action postcondition observation before changing Gamma, Memory, or Planner semantics. Capture an explicit target visibility/presence signal, target identity, and distance when available.
2. Bind Controller return evidence and runtime goal-check evidence into the action label without silently equating terminal task success with action success.
3. Add focused tests proving that an observable successful `find` can become scientific success, an observable bounded failure can become scientific failure, and missing evidence remains audit-only ambiguous.
4. Add an invariant reproducing the `sapling` case: `goal_success=true` must not be discarded solely because `target_visible` was omitted by the adapter.
5. Audit action-signature normalization (`tree`, `oak_log`, `wood`, `redstone_ore`) across Planner, Controller, postcondition registry, and scene exemplar metadata.
6. Run a three-task diagnostic smoke (`sapling`, `iron ore`, and one wood task) after instrumentation tests pass. Do not immediately rerun all nine tasks.
7. Inspect compatible-pool coverage for `find` actions. If the frozen Memory legitimately has no compatible exemplars, exercise the declared degradation path rather than interpreting incompatible-only retrieval as calibrated bilateral evidence.
8. Only after labels become observable should the project evaluate Candidate B/Gamma, expand the engineering pool, or authorize a scientific calibration campaign.

## Questions for the next planning pass

- What exact MineDojo observation should be the authoritative `find` postcondition for blocks, items, and abstract aliases such as `tree` or `wood`?
- Should bounded `find` exhaustion be treated as observable scientific failure when the target-absence evidence is local rather than global?
- How should action-level success and terminal task success be represented together in the decision record schema?
- Does the formal frozen Memory contain any compatible `find:*` exemplars, or is signature normalization preventing matches?
- Should Provider retry accounting remain campaign-local, or move to a provider preflight/availability gate that cannot consume scientific assignment attempts?

Stage results do not justify a paper-level performance claim. They establish that the source-frozen campaign machinery works and isolate the next blocker to evidence observability and action-level labeling.
