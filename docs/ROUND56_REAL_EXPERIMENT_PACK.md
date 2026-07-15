# DC3PA Round 5.6 Real Experiment Pack

Round 5.6 adds an immutable configuration layer for real Minecraft experiments.
It does not alter the DC3PA method, Controller, Trigger, reliability formulas,
or evaluation prompts, and it does not run formal data collection.

## Engineering Scope

- Freeze an author-approved blueprint for final tasks, acquisition assignments,
  development assignments, budgets, model/controller IDs, prompt hashes, and
  Environment candidate grids.
- Bind the frozen blueprint later to real memory, confidence, and selected
  Environment artifacts before generating a bound `DevelopmentProtocol`.
- Track phase completion in an ordered ledger that cannot skip from design to
  holdout or final evaluation.
- Validate packs and generate a current runbook without embedding credentials,
  machine paths, real tasks, seeds, datasets, ledgers, reports, or artifacts in
  Git.
- Provide a hosted synthetic gate for schema and ordering checks only.

## Author Decisions Still Required

The repository intentionally ships only
`MP5_agent/dc3pa/configs/round56_author_experiment_spec.DRAFT.json`. Authors
must copy it outside Git and provide the exact external files for final-test
exclusion, activation policy, data-sufficiency policy, assignments, budgets,
model/controller versions, prompt hashes, and approval records. The builder
refuses `draft_only: true`.

## Approval Flow

1. Fill the external author spec and related policy/exclusion files.
2. Run `build_real_experiment_blueprint.py --print-content-sha-for-approval`.
3. Record the SHA in the author approval record outside Git.
4. Insert the exact SHA into the external spec.
5. Rerun without `--print-content-sha-for-approval` to freeze the blueprint.

Any later blueprint-content change invalidates the approval hash and produces a
new blueprint ID.

## Tiny Dry-Run Recipe

Before formal acquisition, use only a preregistered `dev_train` task-seed and
mark all dry-run outputs excluded from formal fitting:

```bash
cd MP5_agent
python scripts_dc3pa/validate_real_experiment_launch.py \
  --blueprint EXTERNAL_BLUEPRINT_JSON \
  --phase dry_run_completed \
  --task AUTHOR_APPROVED_DEV_TRAIN_TASK \
  --seed AUTHOR_APPROVED_DEV_TRAIN_SEED \
  --max-execution-attempts 1 \
  --run-manifest-id stage6=EXTERNAL_RUN_MANIFEST_ID
```

The command emits a JSON payload suitable for external traces. It does not
start Minecraft and does not invent runner commands or credentials.

## Gate

```bash
cd MP5_agent
python scripts_dc3pa/run_round56_gate.py
```

Hosted CI validates synthetic schemas and ordering. It does not certify that
author decisions are complete, that formal experiments ran, or that paper
claims are supported.
