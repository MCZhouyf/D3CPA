# Round 5.9.4 Formal Log Bootstrap

## Experimental condition

Round 5.9.4 changes the formal environment condition. Results produced with
this policy are **planning-focused log-bootstrap MineDojo** results. They may
be reported as task success under the standardized log-bootstrap condition.
They must not be reported as natural empty-inventory MineDojo performance or
pure natural resource collection.

Episodes begin with an empty inventory. For a plan version that explicitly
declares log acquisition, the Controller performs at most three bounded
natural collection attempts. If the declared target is still unmet, the
runtime adds exactly the positive log shortfall. No other item may be added.
The target is the sum of explicit log-mining action quantities (`step.times`)
in that exact plan version, including normalized item names such as `oak_log`.
Craft materials and recipes are not consulted, so an omitted or insufficient
declaration remains a planning failure.

## Required reporting

Every formal result must preserve these separate outcomes:

- natural completion;
- bootstrap-assisted completion;
- incomplete;
- intervention trigger count and injected log count;
- Planner, Reflection and Evaluation Chain call counts.

Aggregates must retain the policy, amendment, data-binding, Blueprint and
source-commit identities. Datasets or memory snapshots with missing or mixed
bootstrap identities are invalid.

## Runtime boundary

Formal activation requires a frozen policy, frozen ZYF amendment, frozen data
binding, real-experiment Blueprint, approved scope/method, marked external
output root and immutable receipt path. Environment variables alone cannot
activate the intervention. `task_semantic_smoke` remains intervention-free.

The inventory mutation preserves each unrelated MineDojo slot, item name,
variant and quantity, then re-reads the environment. A stale first frame is
tolerated once; a second mismatch fails closed. This intervention does not
change Controller/Evaluator task-success logic.

## Returned-model identity

Every nonempty provider-returned model identity is recorded in run receipts and
Model Epoch evidence. Requested/returned equality and identity stability within
a run, campaign or epoch are not gating conditions under the author-approved
record-only policy. This preserves intermediary variation for audit without
claiming that a returned string proves the identity or stability of hidden
backend weights.
