# Stage 6 Cobblestone Controlled Test Audit Pass 2

## Scope

This pass re-checks the same repository from failure-first and adversarial angles. It
does not repeat the architectural inventory from Pass 1.

## Failure-Mode Findings

### 1. Could a bad initial plan bypass knowledge conflict because pL is high?

No.

- `HybridProbabilityModel` computes the overall probability from available dimensions.
- `AdaptiveTriggerSession.observe(...)` receives an explicit `hard_conflict` flag.
- `AdaptiveCognitiveControlPlanner.plan_with_outcome(...)` sets `hard_conflict = any(result.hard_conflict for result in results)` for the current window.
- `should_evaluate` becomes true when `hard_conflict` is true, even if monitored confidence is above threshold.

Result: a high model score can raise `Pi`, but it cannot suppress evaluation when the knowledge dimension marks a hard conflict.

### 2. What if `hard_conflict=true` but Evaluation Chain returns `accepted=true`?

This is already fail-closed.

- Planner traces `evaluation_report`
- If `report.accepted` and `hard_conflict` are both true, the planner appends an unresolved item with reason `accepted_despite_hard_conflict`
- No patch is applied
- The final `PlanningOutcome.unresolved` remains non-empty
- `Stage6ClosedLoopRunner` blocks execution by default when `unresolved_plan_policy == "block"`

Controller should not run in this case.

### 3. Can Evaluation Report target stale plan IDs, stale versions, or nonexistent step IDs?

No, not silently.

`EvaluationReport.from_dict(..., expected_plan=...)` rejects:

- mismatched `plan_id`
- mismatched `plan_version`
- issue step IDs not present in the expected plan

`PlanEditor.apply(...)` additionally rejects:

- `target_step_id` values missing from the current plan
- duplicate edit IDs
- conflicting terminal edits
- patches that delete every step

The deterministic evaluation provider in the controlled test must derive IDs from the real request object rather than hard-coding them.

### 4. Could stale reliability evidence continue to be used after a patch?

No, not for the revised plan.

- Planner restarts trigger evaluation via `session.restart_after_revision(restart_index, len(plan.steps))`
- `AdaptiveTriggerSession.restart_after_revision(...)` clears `_recent`
- new `ReliabilityResult` objects are recomputed against the revised `plan_id`, `plan_version`, and `step_id`
- `EvaluationRequest.__post_init__` rejects stale reliability results that do not match the current plan

Old reliability history remains in the planning outcome for audit, but not as active evidence for the revised plan.

### 5. Could the Controller receive the original plan instead of the revised one?

The runtime currently sends `decision.plan`, which in `dc3pa` mode is the `outcome.final_plan`.

If a patch is applied successfully:

- `decision.plan` is the revised plan
- `plan_ready_for_controller` event uses that revised plan's `plan_id` and `version`
- `controller.execute(...)` is called with that revised `Plan`

This is testable by having the controlled Controller reject version-1 plans and record the received `plan_id`.

### 6. Could memory be written when Controller says success but Goal Checker says false?

No.

- `goal_success` defaults to false
- when `require_goal_check=True`, `goal_checker.is_done(...)` must return true before `_record_success_memories(...)` is called
- otherwise the runtime falls through to failure handling and reactive replanning
- the final failure path returns `memory_recorded=False`

Existing runtime tests already cover this behavior.

### 7. Could memory write failure mislabel the task result?

Current behavior is explicit and bounded:

- under `memory_failure_policy="trace"`:
  - the task can still return `success=True`
  - failed memory writes emit `legacy_memory_record_failed` or `multimodal_memory_record_failed`
  - `memory_recorded` becomes false if no sink recorded successfully
- under `memory_failure_policy="raise"`:
  - the first memory exception is raised

This is suitable for the controlled test, but the report must distinguish environment/task success from memory persistence success.

### 8. Could repeated runs share SQLite, trace, or temp state and create a false pass?

Yes, if the test reuses directories. The runtime itself does not isolate roots automatically.

Required test discipline:

- create a new temp root for each script run
- create a new `MultimodalMemory` root below that temp root
- write the trace file below that temp root
- do not reuse in-memory world/controller objects across the A/B validation runs

### 9. Could trace leak raw images, vectors, secrets, or absolute paths?

The current trace sanitizer reduces this risk substantially:

- secret-like keys and values are redacted
- `image`, `rgb`, `pov`, `image_vector`, `embedding` are reduced to descriptors
- `Path` values are reduced to `name`
- unknown complex objects are serialized as bounded type descriptors

Residual risk:

- arbitrary free-form strings in application-level payloads may still contain non-secret local context
- the controlled test should avoid embedding temp roots in string payloads where possible

### 10. Which output fields are stable vs. non-stable?

Stable semantic fields for A/B comparison:

- `task`
- `mode`
- `success`
- revision / evaluation / fallback / block / controller counts
- action order in the final plan
- `hard_conflict` flags
- `pK.available`, `pK.probability`, `pK.hard_conflict`
- final inventory quantities
- memory episode count delta
- event type sequence

Non-stable fields that must be normalized before comparison:

- `plan_id`
- `step_id`
- `edit_id`
- `episode_id`
- `exemplar_id`
- `timestamp`
- `created_at`
- `duration_seconds`
- temp-root-dependent filenames

## Admission Decision

READY
