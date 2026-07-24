# DC3PA Round 5.13E5F hardening

## Scope

This round is prospective instrumentation hardening only. It does not relabel
the nine Round 5.13E4 records, fit CHRM, calibrate Model or Environment,
change Candidate B or Gamma, estimate CDT, create formal Development data, or
open Holdout, Final Evaluation, or Round 6.

The frozen E4 public facts remain: 9/9 infrastructure closures, 0 accepted
action labels, 9 `ambiguous_unobservable` action labels, seven Controller
success signals, one terminal-goal success, four classified provider transport
attempts, and zero Memory or Acquisition writes.

## Outcome contract

V4.1.3 stores three independent evidence layers:

- Controller status and Controller evidence IDs.
- Action transition status, `y_action`, and action evidence IDs.
- Terminal goal status, `y_goal`, Evaluator evidence IDs, and terminal-state hash.

`y_action` is the only CHRM-lite primary label. Controller success and terminal
goal success cannot override it. A Goal Evaluator result is binary only when
the Evaluator was actually called; otherwise the goal remains unresolved.

For `find`, success requires a complete trace, canonical identity match,
visibility, a frame ID, and one of the existing Controller spatial relations:
presence in the frozen voxel observation volume or frozen adjacent voxel set.
No new distance threshold was introduced. Scientific failure requires a
complete, technically clean, exhausted bounded search with no identity match.
Missing evidence and safety/unknown stops remain ambiguous.

## Signature policy

Raw task, Planner, Controller, and Scene targets are retained alongside the
canonical object/action signatures and rule IDs. Important mappings are:

| Raw action target | Canonical action object | Relation |
|---|---|---|
| `tree`, `wood`, `log`, `oak_log` | `minecraft:block/log_source` | Controller observation or variant alias |
| `cobblestone`, `stone` | `minecraft:block/stone` | source/product or observation relation |
| `redstone`, `redstone_ore` | `minecraft:block/redstone_ore` | action-source relation only |
| `iron_ore` | `minecraft:block/iron_ore` | exact observation identifier |
| `sapling` | `minecraft:block/sapling` | exact observation identifier |
| `crafting_table` | `minecraft:item/crafting_table` | exact item |
| `wooden_pickaxe` | `minecraft:item/wooden_pickaxe` | exact item |

Task-goal signatures remain distinct from action-source signatures. In
particular, task `redstone` is not task `redstone_ore`, and `iron_ore` is not
`iron_ingot`. Unknown aliases fail closed.

Canonicalization only repartitions Scene metadata compatibility pools. It does
not modify MineCLIP vectors, Scene rows, visual scores, top-k, tie-break,
Candidate B, or Gamma.

## Diagnostic boundary

The exact formal catalog tasks prepared for a later diagnostic are, in order:
`mine sapling`, `mine iron ore`, and `mine log`. Their formal assets are
resolved from the active formal task release, not inferred from names.

The seed policy is intentionally unresolved:

- D1 reuses each corresponding E4 task seed for exact bug-regression replay.
- D2 uses a new diagnostic-only namespace and new seeds for independent
  engineering validation.

Both choices are diagnostic-only and ineligible for formal fitting, channel or
CHRM calibration, CDT identification, Holdout, or Final Evaluation. Until ZYF
chooses D1 or D2 and approves the resulting exact assignment seal, MineDojo
execution and a full nine-assignment rerun remain prohibited.
