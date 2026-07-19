# DC3PA Round 5.12: Round 5.11 Closeout Boundary

## Result

Round 5.12 stopped at the mandatory Round 5.11 closeout boundary. The immutable
closeout report ID is
`4c168032881eda6def4235001bcf43e576e8c1f80601f3e5127acb09237e2e8f` and
its eligibility is `false`.

The campaign outcome accounting itself is valid: 60/60 task-seed units resolved,
45 `dev_train` and 15 `dev_tune`, with 22 task successes and 38 scientific task
failures. The final datasets contain 608 train and 179 tune decision records,
787 total, with no duplicate record IDs or hashes. The final redstone-torch
outcomes remain scientific failures and were not retried after a valid pipeline
result.

Protected-data and memory checks pass. All records bind one Paper Memory V5
release and one snapshot root, snapshot roots are unchanged before/after, and
formal-memory writes, AcquisitionStore writes, Evaluation Chain calls, holdout
access, final-evaluation access, and superseded `mine sand` records are all zero.
The sealed holdout file hash matches the pre-outcome protocol, but its plaintext
was not opened.

## Blocking Retry Audit

The immutable accepted lineages contain 100 attempts: 60 final accepted attempts
and 40 preceding failed attempts across 13 task-seed units. This conflicts with
the campaign summary and accepted baseline count of 20 technical retries.

- All 40 preceding attempts lack a frozen technical-failure category, so their
  membership in the approved infrastructure allowlist cannot be verified.
- Three task-seed lineages exceed the frozen maximum of two technical retries.
- Per-attempt bindings do not record the execution-budget fields required to
  prove that budgets stayed unchanged across retries.
- One failed technical attempt contains 24 partial decision rows. Those rows are
  preserved but correctly excluded from the final 787-record dataset.
- No completed scientific failure was retried, no failed-attempt row entered the
  final dataset, and the recorded task/seed/memory/taskset/prompt/bootstrap
  lineage fields have zero mismatches.

These are provenance and accounting failures. They cannot be repaired by
inferring categories from logs or rewriting immutable attempt metadata after
outcomes are known. A new author-approved protocol decision is required before
Round 5.12 can proceed.

## Artifact Qualification

All nine required Round 5.11 artifacts are present, eligible, and mutually bound:

| Artifact | ID |
| --- | --- |
| SceneLineageAudit | `3567c620b7a59260f63ea2c3fc5a08e56feb38c7f459a327e01b7c5c1cdf6d5c` |
| DevelopmentSplitProtocol | `7e7f0d027ab7d440e20a10f687fe1d063ac11603c347f03638f5d8880723c9cc` |
| Round511AnalysisPolicy | `5b832b3a66ee89d50fcbd38fdf19a2f6b957d854f3feebad319e01b7c9ba5cab` |
| DevelopmentToolingBinding | `f449839ecffe7b2e5541e5ae052444e6eecbdf8e77d84c510315d86fe0e44c60` |
| DevelopmentInputRelease | `bd2f2e96e3e0fd3e4c8dcf4b2180d15adf971d44181ae51bb84c932af0533f99` |
| DevelopmentCollectionAudit | `313b79003396377d6674e5e8a2850a3e4396309c9952324c2158b5251515dda3` |
| ConfidenceCalibrationRelease | `58a7379516f3f3b6a06e21e123ff47a673e6aa9c09c378975a2a160a9ae8e343` |
| EnvironmentEvidenceRelease | `26344d960f505f8a1d4d13b9ad7e209fcfb29dbef437d0f9503639001b0a20c8` |
| FusionFeatureDatasetRelease | `ecb3ef3af7cfa40c6bf083b5917f530d8e192a4411f8b2f262f345bb3d927e25` |

## Direction Review

The frozen raw feature `knowledge_unknown` is an absence/risk indicator and
cannot receive a nonnegative success coefficient. The valid deterministic
parameterization is `knowledge_known = 1 - knowledge_unknown`, followed by
nonnegative coefficients for coverage, known knowledge, confidence probability,
and environment probability. Existing Round 5 code uses an older feature schema,
so it cannot consume the Round 5.11 export without an explicit direction-policy
binding.

No direction policy was frozen and no Fusion candidate was fitted because the
earlier closeout gate is ineligible. The holdout single-use ledger was not
created or consumed, holdout outcomes remain unopened, final evaluation was not
accessed, and Round 6 did not start.
