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
