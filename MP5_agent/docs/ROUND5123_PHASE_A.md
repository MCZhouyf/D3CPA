# DC3PA Round 5.12.3 Phase A

## Scope

Round 5.12.3 starts from public commit
`56a7f09bf7cd64a63e0a6285f0df6ff9a77107bd`. Phase A does not rerun the
completed 60-unit development campaign, fit Fusion, open holdout data, start
final evaluation, or start Round 6.

The author-amended development result remains descriptive: 36 of 60 task-seed
units succeeded and 24 produced scientific failures. It is not a homogeneous,
single-runtime benchmark result.

## Runtime Audit

The immutable evidence resolves to five runtime segments, not three. Segment
boundaries use the complete tuple of source commit, execution-budget snapshot,
Controller bundle, evaluator, prompt bundle, Paper Memory V5 release, active
taskset, and formal Log Bootstrap policy.

| Segment | Source | Explore | Timeout | Units | Decisions | Success/Failure |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | `804c96a` | 60 | 1800 s | 38 | 301 | 35/3 |
| 2 | `5b2f8da` | 120 | 1800 s | 11 | 188 | 1/10 |
| 3 | `5b2f8da` | 120 | 3600 s | 1 | 15 | 0/1 |
| 4 | `5b2f8da` | 120 | 3600 s | 3 | 53 | 0/3 |
| 5 | `6f47526` | 120 | 3600 s | 7 | 124 | 0/7 |

Segments 3 and 4 have the same numeric exploration and timeout settings but
different immutable authorization/snapshot identities, so they remain separate.
Segments 1 through 4 use the same Controller source bundle. Segment 5 changes
`structured_actions.py`; the evaluator identity is unchanged across all five.

All 60 final units and all 681 accepted decision records have exactly one
segment binding. Accepted-data counts are 45/15 units and 528/153 records for
`dev_train`/`dev_tune`. Duplicate accepted record IDs, failed-attempt record
contamination, memory writes, AcquisitionStore writes, Evaluation Chain calls,
holdout/final contamination, and `mine sand` records are all zero.

The one replacement lineage is `dev_train:medium:mine coal ore:3`. Its old
scientific failure contributed 17 rows to preserved historical evidence and
zero rows to the effective dataset; the authorized successful replacement
contributed 8 accepted rows. Exactly one final attempt is selected.

Legacy bootstrap receipts retain an older `source_commit` value. They are not
used as runtime identity. For every accepted unit, `run_binding.json`, the
execution-budget snapshot, decision rows, and source-file hashes agree.

## Stop State

Phase A emits a hash-bound external `RuntimeSegmentManifest` and a DRAFT
`MixedRuntimeDevelopmentAmendment`. The draft cannot create an
`AmendedDevelopmentDatasetAcceptance`; explicit ZYF approval must be supplied
and hash-bound first.

- RuntimeSegmentManifest ID:
  `da833a112b87863262c229a661885fe7072145b688a9f5317c96608d07a1f5b4`
- DRAFT MixedRuntimeDevelopmentAmendment ID:
  `f8e6c5fa3f514f834098be3d3cd1da0028669300d55fdc342c9e662669b69694`
- Amendment status: `DRAFT`; no approval identity, timestamp, or statement is
  populated.

Two additional pre-fit issues remain unresolved:

- No verifiable preregistered L2 candidate grid was found in the Round 5.5 or
  Round 5.5.1 public/external policy artifacts.
- The approved activation policy freezes bootstrap grouping as `task`, while
  the Round 5.12.3 prompt also requires task-seed/run grouping. This conflict
  cannot be resolved after observing outcomes without an explicit author
  decision.

The existing trainer's feature schema is not reused for the amended dataset.
In particular, `knowledge_unknown` is an adverse signal and cannot be assigned
a nonnegative success coefficient. Runtime segment, Controller, source commit,
budget, task, and difficulty remain audit metadata and are forbidden as Fusion
predictive features.
