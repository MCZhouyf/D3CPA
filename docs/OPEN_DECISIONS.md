# Open decisions

## Stage A — frozen memory snapshot required for formal readonly evaluation

`MP5_agent/dc3pa/integration/stage6_config.py:104-107` requires `memory_snapshot_manifest` whenever `memory_mode=evaluate_readonly`. The Stage A `PaperRunConfig` correctly freezes readonly mode and disables both long-term recording paths, but this checkout does not contain an identified, approved frozen acquisition snapshot for the new 50-task registry. A synthetic empty snapshot would not be scientifically defensible.

**Action needed:** provide or approve the exact acquisition snapshot manifest/root to bind to the 50-task evaluation. Until then, A2–A6 runtime quantities must remain unreported; no surrogate memory state will be created.

## Stage A — runtime registry validation

The authoritative `/external/dc3pa/task_assets_schema/task_mapping_manifest.json` marks all 50 candidate targets `candidate_requires_runtime_registry_validation`. The static manifest binds the paths and selects the 10-task, five-tier A3 subset, including `obtain diamond` and `mine redstone`. Before a formal 90-episode run, each selected JSON must be accepted by the actual Stage6/MineDojo task registry under the frozen environment.

**Action needed:** run the additive Stage A launcher once the frozen snapshot is available; it must emit a validation receipt for every selected JSON before any success-rate claim.

## Stage A — no base-code modification proposed

Neither decision requires a change below `MP5_agent/agent/` or `MP5_agent/dc3pa/`. The remedy is an approved snapshot plus an additive runner/configuration only.
