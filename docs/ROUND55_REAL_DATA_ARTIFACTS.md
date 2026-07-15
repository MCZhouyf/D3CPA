# DC3PA Round 5.5 Real-Data Artifacts

Round 5.5 source code defines the preregistered development calibration workflow.
Real development datasets and generated artifacts must stay outside Git.

Recommended external layout:

```text
round55-real-calibration/
  protocol/
    activation_policy.json
    development_protocol.json
    data_sufficiency_policy.json
  datasets/
    dev_train.jsonl
    dev_tune.jsonl
    dev_holdout.locked.jsonl
  artifacts/
    ordinal_confidence_artifact.json
    frozen_memory_snapshot/
    fusion_candidate.json
    fit_train_tune_report.json
  holdout/
    holdout_activation_report.json
  release/
    paper_fusion_release.json
```

Rules:

- Hash and freeze the activation policy and development protocol before opening
  locked holdout labels.
- Fit with `fit_monotonic_fusion_three_way.py` using only `dev_train.jsonl` and
  `dev_tune.jsonl`.
- Evaluate the locked holdout once with `evaluate_fusion_holdout.py`; the report
  refuses overwrite.
- Create `paper_fusion_release.json` only from an eligible holdout report.
- Keep final 50x30 test outputs out of all Round 5.5 fitting and activation
  inputs.
- Hosted CI uses synthetic fixtures only and does not prove scientific
  activation.
