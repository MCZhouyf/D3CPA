# DC3PA Round 5.9: model epoch and acquisition readiness

Round 5.9 adds fail-closed gates between the hosted Round 5.8 integration and
formal experience acquisition. It does not implement Trigger V2 or mark any
draft method ready.

Schema-v1 and schema-v2 reference designs must be regenerated externally from
the same 50-task catalog and compared with
`compare_round58_design_semantics.py`. A new external approval binding records
the eligible migration report, schema-v2 design, mutable `gpt-5.1` risk,
12-hour epoch policy, and interleaved schedule policy. Old approval hashes are
not translated or reused.

Model epochs use immutable open and closed files. Start and end probes call the
public metadata-preserving Responses adapter and retain only model/profile,
timing, response-ID hash, and usage scalars. A model/profile/endpoint/context
mismatch, text logging, failed probe, or duration over twelve hours creates an
invalid epoch. Alias equality cannot detect hidden backend-weight changes.

Stage6 dry-run receipts contain the effective seed read from the Evaluator that
constructs MineDojo, environment and Controller startup, returned model IDs,
explicitly preregistered expected calls, actual provider calls, formal-memory
status, dry-run guard, technical failures, and trace hash. Task failure remains
separate from pipeline failure.

The final readiness audit requires an eligible semantic migration and approval
binding, matching Blueprint validation, a validly closed epoch, the full
MineDojo marker, Basic/Medium/Complex truth receipts, and an eligible six-entry
dry-run audit. `advance_round59_dry_run_phase.py` advances only an eligible
report and binds both readiness and epoch IDs to the phase record.

Generated designs, approvals, probes, epochs, schedules, receipts, traces,
task lists and credentials remain outside Git. Hosted CI is synthetic and
cannot establish full MineDojo or formal acquisition readiness.
