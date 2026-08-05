# G0 final report

G0 establishes an auditable no-task-privilege baseline from `success-finish`
(`06a708e2dcfc6bb83d48e41b1475cf0581db15d5`). The authoritative machine
summary is `runs/g0/stage0_audit.json`.

## Results

- The external formal catalog still has exactly 50 tasks: 37 craft, 11 mine, and
  2 smelt. The user-authorized structured rule treats `obtain diamond` as a mine
  terminal task; task files were not edited.
- The protected log callback AST and protected internal call expressions match
  `success-finish`; its dynamic trace retains the existing 100-step delay and a
  single log-only inventory write.
- The effective Controller dispatches only the final G0 definitions. It executes
  declared low-level actions or returns an auditable structured failure; it does
  not insert planner steps, mutate a planner workflow, set inventory, or branch on
  a task/item label. The effective-policy audit is in
  `runs/g0/formal_policy_audit.json`.
- Missing mine, craft, and smelt prerequisites are regression-tested to preserve
  inventory and the planner workflow. Existing tests that asserted the retired
  automatic recovery behavior were changed to assert the stronger G0 behavior,
  rather than skipped or relaxed.
- `configs/g0_runtime.json` centrally defines the relay endpoint/model (without
  credentials), seed, uniform budgets, and disabled recovery/memory flags. The
  launcher resolves CLI > environment > config and records a redacted resolved
  configuration; Planner, Work_Memory, and Reflexion each receive the resolved
  temperature, top-p, max-token, and retry values. `EPISODE_SEED` drives both
  MineDojo seeds, Python random, and NumPy with no random fallback.

## Validation

Two independent complete passes succeeded:

- MP5/DC3PA: 222 passed.
- Stage-A support tests: 16 passed.

The exact commands and outputs are retained in `runs/g0/test_results_pass1.txt`
and `runs/g0/test_results_pass2.txt`. G0 only used deterministic local fixtures
for seed validation and did not start Minecraft or send a task to the configured
relay.

## Scope boundary

This report does not claim a formal success-rate experiment. G0 deliberately
stops after baseline sanitisation and validation; G1 mechanisms and formal
episodes remain out of scope.
