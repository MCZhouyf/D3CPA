# DC3PA Round 5.12.4 Standard Development Closeout

## Scientific Decision

The author accepts the completed 60-unit campaign as one standard development
experiment. The Controller repairs and execution-budget adjustments are treated
as execution-layer fixes, not changes to the scientific method. No development
unit or accepted decision record was rerun, removed, reweighted, or stratified
by source, Controller, runtime segment, task, difficulty, or budget.

The historical RuntimeSegmentManifest remains available for engineering audit.
It is neither an eligibility gate nor a Fusion predictive feature.

## Integrity

- Units: 60 resolved, 45 train, 15 tune.
- Outcomes: 36 task successes and 24 scientific failures; development success
  rate is 0.600.
- Decision records: 528 train and 153 tune, 681 total.
- Train labels: 448 correct and 80 incorrect.
- Tune labels: 128 correct and 25 incorrect.
- Failed-attempt contamination, duplicate accepted IDs, formal-memory writes,
  AcquisitionStore writes, Evaluation Chain calls, holdout/final accesses, and
  `mine sand` records are all zero.
- All accepted records bind one Paper Memory V5 snapshot root.

The resumed `dev_train:medium:mine coal ore:3` lineage contains one old failed
attempt with 17 decision rows. None enter the accepted dataset. Its resumed
successful attempt contributes eight rows, and exactly one final attempt is
accepted for the assignment.

## Frozen IDs

- StandardizationDecision:
  `7727da5900cc1244973a48cdac240f036939fec9e2904724177b2bbe8b7d6e23`
- StandardDevelopmentDatasetAcceptance:
  `64c1b1db52b206162e2b26231db02fa5aeead4703eeabf220de7b5fc31597e11`
- StandardDevelopmentCloseout:
  `da9a01ff03cfce6efbb2eda303bfc8ddccf2828829cf2948fb3dbe1cae46ad7e`
- L2ProvenanceAudit:
  `41db0ae0a833bfabb980e6d46cff7f3d1792b13e6177ca4c7756733bb89b04cd`
- Round5124BootstrapPolicy:
  `11cfb90bb35f2cd5a995810382f5db35d5d19fca18a8987d66ac282d002c0ce8`

## Modeling Policy

The L2 provenance result is Case 2. Commit `208ebf9` froze a single historical
value, `l2=1e-3`, in both TrainerConfig and the fitting CLI before the current
development outcomes existed. It therefore becomes a one-element grid; tune
may select a checkpoint but may not select L2.

The historical trainer uses mean binary negative log-likelihood with the
equivalent penalty `0.5*l2*sum(beta_j^2)`. The intercept is not regularized,
features remain on their native `[0,1]` scale, and decision records are equally
weighted.

Primary activation uncertainty uses task-grouped bootstrap with 2,000
replicates, seed `5102026`, and 10 reliability bins. Task-seed/run grouping is
supplementary sensitivity only and cannot override the primary activation
decision. Decision-row IID bootstrap is forbidden.

At this closeout point, Fusion remains unfitted, holdout remains unopened,
final evaluation remains unopened, and Round 6 has not started.
