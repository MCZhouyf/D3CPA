# DC3PA Round 5.11 Development Campaign Results

## Status and Scope

The V5 development campaign completed all 60 authorized `dev_train` and
`dev_tune` assignments. It produced 787 immutable decision records: 608 train
records and 179 tune records. The collection audit is eligible, with no duplicate
records, no holdout access, no final-evaluation access, and no formal-memory or
acquisition writes.

This is development evidence, not a final evaluation result. The campaign began
from source commit `1a949ac323e759e54327d44ca352af2ab64245b5` and received
Controller/runtime fixes while collection was in progress. Those fixes are
captured by commit `a76f5a20e225a3bd0d6fe530a67b065a24aa3434`. Consequently,
the 60 runs do not represent one clean, immutable runtime revision and must not be
reported as a single-source reproducibility result.

## Campaign Aggregate

- Assignments completed: 60/60
- Successful assignments: 22/60 (36.7%)
- Failed assignments: 38/60 (63.3%)
- Distinct tasks: 20
- Seeds per task: 3
- Technical-failure attempts observed by the campaign runner: 20
- Evaluation-chain calls: 0
- Controller intervention triggers: 66
- Log bootstrap injections: 123
- Naturally collected logs: 16
- Collection ID: `ecd2a62f84ac0b13e418d731ebd37f2f319159c08bdb16a71037cc975f2828bc`

| Task | Successes | Runs |
| --- | ---: | ---: |
| craft boat | 0 | 3 |
| craft button | 3 | 3 |
| craft cauldron | 0 | 3 |
| craft chest | 3 | 3 |
| craft compass | 0 | 3 |
| craft diamond axe | 0 | 3 |
| craft fence | 1 | 3 |
| craft furnace | 0 | 3 |
| craft iron trapdoor | 0 | 3 |
| craft piston | 0 | 3 |
| craft redstone torch | 0 | 3 |
| craft shears | 0 | 3 |
| craft stick | 3 | 3 |
| craft stone shovel | 1 | 3 |
| craft stone sword | 3 | 3 |
| craft wooden axe | 1 | 3 |
| mine coal ore | 2 | 3 |
| mine log | 3 | 3 |
| mine wheat seeds | 2 | 3 |
| smelt iron ingot | 0 | 3 |

The runtime fixes improve bounded log acquisition, crafting-table placement and
reuse, structured crafting recovery, and coal-ore completion semantics. They do
not turn this mixed-revision development campaign into a clean final benchmark.

## Audit and Frozen Outputs

The development collection audit reports `eligible=true` for 787 records across
60 task/seed runs. It found zero duplicate records, zero holdout records, zero
formal-memory writes, and zero acquisition writes. The read-only snapshot root was
stable at
`af9523e3fd4fc6958916f4585f3edc0f522568b181f969840f154a720092f353`.

- Collection audit ID: `313b79003396377d6674e5e8a2850a3e4396309c9952324c2158b5251515dda3`
- Confidence release ID: `58a7379516f3f3b6a06e21e123ff47a673e6aa9c09c378975a2a160a9ae8e343`
- Environment release ID: `26344d960f505f8a1d4d13b9ad7e209fcfb29dbef437d0f9503639001b0a20c8`
- Fusion feature dataset release ID: `ecb3ef3af7cfa40c6bf083b5917f530d8e192a4411f8b2f262f345bb3d927e25`
- Train feature dataset ID: `49f98bcd1af429d694e2a327a09bdf7a826ce4185508b53f3188476542be524a`
- Tune feature dataset ID: `bf4ab7ee67f0428179bf010007226d939f3200dc711e5b93378659edb6602046`

The ordinal confidence release is monotonic and eligible. Train metrics are
accuracy 0.8092, Brier score 0.1382, ECE 0.0040, and log loss 0.4406. Tune metrics
are accuracy 0.7430, Brier score 0.1634, ECE 0.0658, and log loss 0.5020.

The selected environment candidate is
`0aaa2944f30fb785f25c07e6887792741b48d067e2be2bbc2dc593359ea5662c`.
Its tune accuracy is 0.7430, Brier score 0.1972, log loss 0.5921, and unknown
rate 0.9106. The high unknown rate is a material limitation of this development
collection and should not be hidden by the aggregate accuracy.

Fusion features were frozen in the required order, but Fusion was not fitted.
The frozen release contains 608 train and 179 tune rows and records hard
feasibility as an external gate. Holdout and final evaluation were not used.

## Integrity and Verification

- Campaign summary SHA-256: `ad638006ee8f9baa4bcff6cbd01a47f5ee17cd48c7ee3e83f9d32f85e1cf5781`
- Train decision JSONL SHA-256: `62f33adecff49a0924e3aeac46bc27233f06dec4c48298b7f052db1f4645af50`
- Tune decision JSONL SHA-256: `ce5d479c10a57e9178ef131e9b65c458b69aeff344d0b2030395f9e1c903c7d4`
- Combined decision JSONL SHA-256: `f3d4254cc849e34be32011f14f396b15e290479ebf5b7c39aa7dfa9d04ac5307`
- Frozen train feature JSONL SHA-256: `740b8dd98e430c1c5d9276301bf3e21be4ba5b46dfcbf67c27b5294dfcdd1600`
- Frozen tune feature JSONL SHA-256: `b6b67c0b2edb94e37ba2a2233e05d108f3f5cd0005f50a8b872baa0ebf9af1bf`

Validation after the Controller/runtime fixes:

- Round 5.11 gate: 17 passed
- Full `tests_dc3pa` suite: 546 passed, 1 warning
- Git diff whitespace check: passed
- Repository secret scan: passed

Raw assignments, decision records, receipts, traces, model outputs and
identities, calibration release files, frozen feature rows, credentials, and
machine-specific paths are intentionally excluded from Git. Round 6, holdout
analysis, final evaluation, Trigger fitting, and formal memory acquisition were
not started.
