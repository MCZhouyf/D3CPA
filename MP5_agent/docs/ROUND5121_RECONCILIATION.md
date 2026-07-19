# DC3PA Round 5.12.1: Protocol Reconciliation

## Frozen boundary

Round 5.12.1 started from commit
`469c98ad085e2b8d68acbd92208d7a635492ebe6` and preserves the ineligible
Round 5.11 closeout
`4c168032881eda6def4235001bcf43e576e8c1f80601f3e5127acb09237e2e8f`.
No original attempt, trace, receipt, decision record, or release was rewritten.

The reconciliation policy ID is
`eac84b1daf8f3ec07ccb769a65e6064849d34960cef59b96730066250149c75c`.
It reuses the original nine-category technical-failure taxonomy, keeps the
original initial-attempt-plus-two-retries maximum, rejects free-text and LLM
classification, and freezes the provenance hierarchy for the three discovered
missing budget fields. The public approval contract remains a DRAFT. No policy
approval or remediation approval was supplied.

## Evidence reconciliation

The technical reconciliation ID is
`205a1d4cc9161fd9cfe6715b99926ea12b206e488c8c1bd51f49681ca5bc3a39`.
Of 40 preceding failed attempts, 18 are proven `infrastructure_timeout`, one is
proven `process_crash` from a process signal, and 21 remain `unclassifiable`.
The failed attempts produced 24 decision rows, and zero entered the accepted
train/tune datasets.

The budget reconciliation ID is
`01deee7bde5b2146e72f2f3f44e7ba168d70521a1481de8df34292ea06347e6f`.
All 100 attempts were audited across 300 missing fields. The frozen source and
attempt source binding prove 200 values: `max_execution_attempts=4` and
`max_explore_steps=60` for every attempt. The 100
`episode_timeout_seconds` values are unprovable because the runner allowed a
CLI override and persisted no attempt-time command manifest. There are zero
complete budget profiles and one proven partial profile.

The three retry-invalid units are:

| Role | Group | Task | Seed | Attempts |
| --- | --- | --- | --- | --- |
| `dev_train` | `dev_train:complex:craft compass:3` | `craft compass` | `688051724` | 21 |
| `dev_train` | `dev_train:medium:craft stone shovel:3` | `craft stone shovel` | `2058483124` | 6 |
| `dev_train` | `dev_train:hard:craft cauldron:1` | `craft cauldron` | `1008611961` | 6 |

## Salvage decision

The immutable salvage-decision ID is
`93995a764e669a56c1808b7103b347093754e698c9f91d62048a84e9450692e8`.
Unclassifiable technical failures and unprovable budgets make selective
replacement invalid. The scientifically required remediation is Path B, a
fresh 60-unit campaign. Because no prospective ZYF Path B approval exists, the
currently selected path is Path C and `salvage_status=blocked`.

The prospective runner now rejects retry three before environment launch,
records failure category and structured signal at source, writes the complete
budget snapshot before launch, quarantines failed-attempt decisions, atomically
materializes only accepted final-attempt records, and resumes idempotently after
a receipt/materialization interruption. These safeguards do not authorize a
run by themselves.

No MineDojo remediation run occurred. No reconciled dataset, Confidence
release, Environment release, Fusion-feature release, or reconciled closeout
exists. Holdout remained unopened, Fusion remained unfitted, final evaluation
remained unopened, and Round 6 did not start.
