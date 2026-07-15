# DC3PA Round 5.7 Author Decisions And Tiny Dry Run

Round 5.7 adds tooling for compiling external author decisions and auditing a
tiny dry-run pipeline. It does not select tasks, generate seeds, approve a
Blueprint, run MineDojo, or change the DC3PA method.

## External Sequence

1. Initialize an external workspace:
   `python scripts_dc3pa/init_author_decision_workspace.py --output-dir AUTHOR_WORKSPACE`
2. Authors fill CSV/JSON files and maintain prompt files outside Git.
3. Compile the pre-approval pack with explicit `--prompt NAME=PATH` inputs.
4. Review `author_review.md` and `author_decision_pack_manifest.json`.
5. Run the existing Blueprint builder with `--print-content-sha-for-approval`.
6. Record author approval outside Git and insert the exact content SHA.
7. Freeze the Blueprint with the existing Round 5.6 builder.
8. Initialize phase state, then build a one-to-six-entry dev_train campaign.
9. Run each campaign entry in the full Minecraft environment with explicit
   dry-run receipt arguments.
10. Audit receipts with `audit_tiny_dry_run.py`.
11. Advance `dry_run_completed` only after the audit report is eligible, binding
   the audit-report hash in the phase ledger.

## Boundaries

- CSV headers are exact; extra columns, placeholders, duplicate rows, malformed
  seed indices, empty prompts, and nonempty output directories fail closed.
- All final tasks and all 1500 final task-seed pairs must be explicit.
- The compiler emits a pre-approval spec with pending approval fields; it cannot
  freeze a Blueprint ID.
- Tiny dry-run campaigns select only preregistered `dev_train` groups.
- Dry-run outputs are marked with `.dc3pa_dry_run_root.json` and are permanently
  excluded from formal memory construction, calibration, fitting, and holdout.
- Task completion is informational for the dry-run audit; technical failures,
  secret/RGB leaks, formal-memory use, or formal-fitting inclusion fail the
  pipeline.

Hosted CI uses synthetic author files and receipts only. It does not certify
author approval or real MineDojo dry-run completion.
