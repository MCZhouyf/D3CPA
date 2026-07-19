# Round 5.12.2 Path B Prelaunch Status

## Scope

This engineering change adds fail-closed authorization, complete-budget and
fresh-campaign contracts for a prospective Path B development campaign. It does
not authorize or execute MineDojo, fit Fusion, open holdout/final data, or start
Round 6.

## Frozen Reusable Inputs

- Assignment manifest: `90553e430d1effc09ef95f6afa995c64e26d60fdcd432212496a1ff3c444c406`
- Development protocol: `7e7f0d027ab7d440e20a10f687fe1d063ac11603c347f03638f5d8880723c9cc`
- Active taskset: `a858e28ded81743e9c2f425afa8f62663be37149a819764c6515627e89473215`
- Paper Memory V5: `cc2310aeb60f63e6a1896a4c05109a1ec391649ce102e11b65b6343605789813`
- Paper Memory V5 root: `af9523e3fd4fc6958916f4585f3edc0f522568b181f969840f154a720092f353`
- Formal Bootstrap policy/amendment: `29373c15...` / `4421149a...`

The mounted development assignment file was verified locally as exactly 60
units, 45 `dev_train` and 15 `dev_tune`, with the assignment manifest above.
No outcome from the old campaign is read by the new campaign initializer.

## Fail-Closed Boundary

The real development runner now requires external Path B approval, complete
execution-budget and fresh-campaign authorization documents. It has no partial
assignment `--limit`, timeout override, or retry-limit override. The runner
validates all 60 assignments, protected source hashes, immutable input IDs,
authorization bindings and an absent/empty campaign root before initialization.
It persists the complete budget before each launch and repeats the ledger,
source, assignment and budget checks immediately before subprocess creation.

Attempt indices are fixed to 0, 1 and 2. Attempt 3, a scientific completion or
an unclassified technical failure is rejected before process creation. Failed
attempt decisions remain outside accepted datasets; accepted materialization is
deterministic and idempotent.

## Authorization Status

- Path B approval ID: not issued
- CompleteExecutionBudgetContract ID: not issued
- Explicit `episode_timeout_seconds` author decision: absent
- FreshDevelopmentCampaignAuthorization ID: not issued
- Fresh campaign ID/root: not created
- Real MineDojo attempts: 0
- Fresh component releases/closeout: not created

The repository contains only invalid-by-design DRAFT templates. No approval is
committed to Git. The campaign must remain blocked until ZYF supplies an
external, timezone-stamped, hash-bound approval and explicitly freezes every
budget field, including `episode_timeout_seconds`.

## Preserved Boundaries

The historical ineligible Round 5.11 evidence and its 608/179 decisions remain
unchanged and are not reused. Holdout plaintext remains sealed and unopened.
Fusion remains unfitted; final evaluation and Round 6 remain unstarted.
