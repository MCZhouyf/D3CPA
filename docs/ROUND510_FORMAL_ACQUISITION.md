# DC3PA Round 5.10 formal acquisition

## Baseline and review

The immutable scientific parent is
`540e83f9d75358e1eacb218bfc75fc4ae41f3b9c`. Before integration, every prior
hosted gate passed and the frozen 100-entry schedule was verified to contain
100 ordered, unique task-seed pairs.

Two independent reviews traced schedule-to-ledger execution and successful
Scene-to-snapshot persistence. The supplied overlay was not executed blindly.
Repository-specific corrections were required for:

- deterministic attempt IDs and idempotent, no-overwrite acquisition writes;
- technical failures that occur before a trace or provider response exists;
- removal of a circular acquisition-record/attempt-receipt hash dependency;
- Stage 6 campaign, entry, retry, seed and source-commit binding;
- scene-only online memory with zero online dependency edges;
- Git-computed protected source identities;
- final-test seed contamination and per-image integrity checks;
- regeneration of the schema-v2 manifest after Round 5.10 metadata is bound.

## Runtime invariants

Formal acquisition is accepted only in `reasoning_only` mode with the approved
`single_chain_reactive_acquisition` method, formal Log Bootstrap, four total
execution attempts (initial plan plus at most three reactive replans), and one
frozen schedule entry. Evaluation Chain, Dual Chain, Reliability/Fusion and
Adaptive Trigger do not enter this execution path. The Controller, Evaluator,
task catalog and prompt sources are protected by the source-extension audit.

Successful trajectories are first staged outside Git. After the final trace and
raw Stage 6 receipt identity exist, the record is promoted once to the formal
AcquisitionStore with complete provenance. Divergent replay is rejected; exact
replay is idempotent. Failed attempts are ledger-only and cannot write successful
acquisition records.

## Validation

Run before formal execution:

```bash
cd MP5_agent
python scripts_dc3pa/run_round510_gate.py
python -m pytest -q tests_dc3pa
python -m pytest -q -m minedojo
git diff --check
```

The final source SHA must be committed before freezing the source-extension
audit, tooling binding, retry policy, campaign and 100 ledgers. External
receipts, traces, images, databases, manifests and phase state must remain
outside Git.

## Encoder stop condition

The final paper snapshot requires explicitly approved real image and text
encoder factories. `RGBHistogramEncoder`, `HashingTextEncoder` and development
encoders are rejected. Formal memory release must stop if real encoder weights,
factories or identities are unavailable; no fallback may be described as
MineCLIP or as a paper-level reproduction.
