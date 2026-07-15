# DC3PA Round 5.5.1 Experiment Safety

Round 5.5.1 hardens the real-development workflow. It does not change the
Controller, Trigger, Evaluation prompts, or reliability formula.

Real experiment files must stay outside Git:

```text
round551-experiment-safety/
  exclusions/final_test_exclusion.json
  protocols/development_protocol.json
  collections/{dev_train,dev_tune,dev_holdout}.collection.json
  datasets/{dev_train,dev_tune,dev_holdout}.jsonl
  artifacts/fusion_candidate.json
  locks/holdout_lock.json
  ledgers/holdout_attempt.json
  reports/holdout_activation_report.json
  releases/paper_fusion_release.json
```

Rules:

- Freeze final-test task and seed exclusion before any development collection.
- Store per-example provenance for protocol, exclusion, memory, confidence,
  Environment parameters, feature schema, and source commit.
- Run train/tune preflight without a holdout argument.
- Create a holdout lock before evaluating holdout outcomes.
- Evaluate a locked holdout once through the attempt ledger; ineligible reports
  are completed scientific outcomes, while exceptions are failed attempts.
- Create a paper release only from an eligible locked report and keep paper mode
  in shadow otherwise.
- Hosted CI uses synthetic fixtures only and does not prove real-data
  eligibility.
