# DC3PA Round 5.12.6S and 5.13A-B

## Scope

The pending Round 5.12.6 holdout is superseded before assignment generation.
No assignment or ledger was created, no bundle was read, and MineDojo, final
evaluation, and Round 6 remain closed. The old monotonic Logistic candidate is
retained only as `OldMonotonicLogisticBaselineRelease` for later comparison.

Round 5.13 freezes the CHRM-lite + CDT-lite V4.1 method contract and audits
historical compatibility. It does not fit CHRM-lite, estimate CDT parameters,
or run an active trigger.

## V4.1 Corrections

- The intercept is fitted and unregularized. `beta_K`, `beta_L`, and `beta_E`
  are nonnegative; `beta_U` is unrestricted.
- Verified hard constraints are excluded from soft coverage and bypass Fusion
  and smoothing when violated.
- Model confidence is one of five ordinal levels emitted in the same Planner
  generation. A separate online confidence call is forbidden.
- Environment evidence is deterministic bilateral top-3 retrieval. Either
  under-covered side maps the feature to `unknown`.
- Primary fitting is unweighted step-level NLL plus L2 on coefficients only.
  Cross-fitting and primary bootstrap use terminal tasks; decision-row IID
  bootstrap is forbidden.
- CDT uses planner-equivalent calls. There is no moving-average state and no
  redundant maximum-interval trigger. Its threshold is zero when expected
  correction benefit does not exceed evaluation cost.
- Path A means matched-state paired replay. Path B is observed successful
  revision yield and is explicitly noncausal. `c_fp` includes zero cost when
  Evaluation does not change an already-correct action.
- `L_fail` combines downstream compute with an unrecovered terminal penalty
  derived from remaining episode time and development-only planner-call cost.

## Historical Audit Boundary

The real-data auditor is read-only and requires mounted immutable artifacts.
Hosted CI uses synthetic contract tests only. It never calls an LLM or
MineDojo and never copies decision rows or traces into the repository.

## Historical Audit Result

The read-only audit was run against the accepted Standard Development
artifacts. It verified 528 `dev_train` rows (15 terminal tasks and 45
task-seed/run groups) and 153 `dev_tune` rows (5 terminal tasks and 15
task-seed/run groups). The immutable file hashes are:

- `dev_train`: `f1336cc0143560695cfc63cbd674e6f230aab16952ec50ee3ba457327e236abd`
- `dev_tune`: `7a04b55d3f345b9e7fb0e6d37f8bd58459f2bb2d7a6f21afb8ac033f79515a0e`

The audit found no duplicate record IDs, terminal-task split overlap,
holdout/final rows, or failed technical-attempt contamination. It verified all
60 accepted attempts and trace files without modifying an input artifact.
Paper Memory V5 remained bound to release
`cc2310aeb60f63e6a1896a4c05109a1ec391649ce102e11b65b6343605789813`
and snapshot root
`af9523e3fd4fc6958916f4585f3edc0f522568b181f969840f154a720092f353`.

The `FeatureAvailabilityMatrix` ID is
`ded956f8b830ebe111850226f0d962897f7f541e1962e9b55fd8a73293431982`.
All 681 rows contain an action signature and a five-level confidence value,
but none proves same-generation Planner confidence. All confidence values came
from a separate provider call. V4.1 Knowledge is fully reconstructable for
0/681 rows and 0/20 tasks because frozen per-rule hard/soft classes and
satisfaction lineage are absent. Positive Environment evidence exists for
37/681 rows, but bilateral retrieval coverage is 0/681 because no negative
pool or query-observation lineage was recorded. The historical main label is
present on 681/681 rows but fully joined on 0/681; all 681 remain ambiguous
under the stricter V4.1 label contract.

The CDT identifiability audit ID is
`792dc47227631229fd2bfcb9df53a430cc37a1f9cdc2c70e2ac4f3c0504a4f00`.
Evaluation calls, matched-state replay pairs, Path A evidence, Path B evidence,
`c_eval`, `c_fp`, and both `L_fail` components each have zero historical
observations. No CDT parameter was estimated.

The frozen historical decision is **D (incompatible)**, decision ID
`82de675a8f9b37cfdb06f7d74f75b2b6e9b55561bf5299a7b1f6c2da9f429e89`.
Historical CHRM reconstruction and CDT identification are forbidden because
the hard/soft Knowledge lineage, same-generation confidence proof, bilateral
Environment evidence, fully joined deployment-step label, and Evaluation/CDT
evidence are missing. A targeted new development collection is required before
fitting V4.1. No holdout was accessed and no MineDojo campaign was started.
