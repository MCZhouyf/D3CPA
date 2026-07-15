# Round 5.9.2 pre-acquisition evidence

Round 5.9.2 stops after the `dry_run_completed` phase. It does not start the
100 formal experience-acquisition episodes.

## Required external evidence

The following immutable artifacts remain outside Git and are supplied to the
Round 5.9.2 CLIs through explicit paths:

- the author-approved taskset amendment and final taskset release;
- six controlled task-semantics receipts;
- same-catalog reconstructed-v1 and schema-v2 migration evidence;
- prompt, Controller and Evaluator identities plus Blueprint approval;
- machine-generated MineDojo marker evidence;
- start/end provider probes and a closed model epoch;
- six excluded tiny dry-run receipts and their audit;
- acquisition-readiness and pre-acquisition reports;
- the append-only phase ledger.

The repository does not treat environment construction or process exit code
alone as success evidence. Readiness validates the bound report identities,
effective seeds, returned model IDs, provider-call counts, technical failures,
formal-memory exclusion and the final taskset release.

## Dry-run boundary

Formal tiny dry runs use `reasoning_only`, one execution attempt and disabled
memory. Task completion is informational for this pipeline gate. A failed
Controller attempt invokes the existing Reflexion path, so the expected call
count is one planning call plus one reflection call; a successful attempt has
one planning call.

The launcher sets `DC3PA_MAX_EXPLORE_STEPS=16` only in dry-run mode. This
prevents one `find` action from consuming the entire episode budget while
leaving the legacy default unchanged outside the formal dry-run launcher.

## Model limitation

Both epoch probes and all dry-run responses must report `gpt-5.1` with low
reasoning effort. Matching a mutable model alias does not prove that hidden
provider weights remained unchanged; the model-epoch record preserves this
limitation.

## Phase advancement

`advance_round592_dry_run_phase.py` fails closed unless the pre-acquisition
gate permits both acquisition and phase advancement. The resulting
`dry_run_completed` record binds the gate, readiness, closed epoch, Blueprint,
final taskset release and semantic migration IDs.
