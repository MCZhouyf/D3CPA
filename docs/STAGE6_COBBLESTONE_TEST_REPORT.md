# Stage 6 Cobblestone Controlled Test Report

## Repository And Environment

- Repository: `MCZhouyf/D3CPA`
- Branch: `stage6-integration`
- HEAD: `8c3f19712631631ff33c08028b39f0d0c4926be6`
- Python: `3.10.8`
- Test interpreter: `/root/miniconda3/envs/MP5_agent/bin/python`

Baseline commands:

- `git status --short`: clean before this task
- `git branch --show-current`: `stage6-integration`
- `git rev-parse HEAD`: `8c3f19712631631ff33c08028b39f0d0c4926be6`
- `git tag --points-at HEAD`: no output

## Audit Summary

Pass 1 report: `docs/STAGE6_COBBLESTONE_TEST_AUDIT_PASS1.md`

Verified points from Pass 1:

- Current Stage 2-6 modules exist at the expected repository paths.
- `mine`, `craft`, and `equip` action schemas match the controlled-test plan design.
- knowledge hard conflicts are emitted from the real `KnowledgeReliabilityStrategy`
  with structured missing-prerequisite evidence.
- adaptive triggering can force evaluation on `hard_conflict=True` even with high
  average confidence.
- patched plans really get `version + 1`, fresh `plan_id`, and
  `parent_plan_id = old.plan_id`.
- Stage 6 sends only the finalized plan to the Controller.
- successful memory writes occur only after verified goal success.

Pass 2 report: `docs/STAGE6_COBBLESTONE_TEST_AUDIT_PASS2.md`

Verified points from Pass 2:

- `accepted=true` on a hard conflict becomes unresolved and is blocked before
  Controller execution.
- stale evaluation IDs, versions, or step references are rejected by the real
  evaluation contracts and editor.
- post-patch trigger confidence history is cleared before revalidation.
- Controller success with Goal Check false does not write successful memory.
- memory-write failures are explicitly traced and do not silently alter the task
  outcome semantics.
- repeated runs must use fresh temp roots; the test harness now enforces that.

Admission decision from Pass 2: `READY`

## Files Added

- `MP5_agent/scripts_dc3pa/stage6_cobblestone_controlled_test.py`
- `MP5_agent/tests_dc3pa/helpers_stage6_cobblestone.py`
- `MP5_agent/tests_dc3pa/test_stage6_cobblestone_controlled.py`
- `docs/STAGE6_COBBLESTONE_TEST_AUDIT_PASS1.md`
- `docs/STAGE6_COBBLESTONE_TEST_AUDIT_PASS2.md`
- `docs/STAGE6_COBBLESTONE_TEST_REPORT.md`

## Controlled Test Data Flow

The main controlled test exercises the real Stage 2-6 path:

1. `ControlledStateProvider` creates a real `StateSnapshot` / `AgentState`
2. `ControlledReasoningChain` returns a version-1 defective `Plan`
3. real `build_hybrid_probability_model(...)` computes knowledge/model/environment
   reliability
4. real `AdaptiveCognitiveControlPlanner` runs trigger windows
5. real `StructuredEvaluationChain` parses a deterministic provider response
6. real `PlanEditor` applies the patch and creates version 2
7. real planner re-evaluates the revised plan
8. real `Stage6ClosedLoopRunner` emits `plan_ready_for_controller`
9. controlled Controller executes only the revised plan
10. controlled Goal Checker verifies the final inventory
11. real `MultimodalMemory.record_success(...)` writes the successful episode and
    two scene exemplars

No real LLM, MineDojo, Minecraft, MineCLIP, API key, or network call was used.

## Initial Defective Plan

The deterministic reasoning plan is:

1. `find cobblestone`
2. `mine cobblestone` with `tool="wooden pickaxe"` and `times=4`

It intentionally omits both:

- `craft wooden pickaxe`
- `equip wooden pickaxe`

Initial controlled inventory:

```json
{
  "planks": 3.0,
  "stick": 2.0,
  "crafting table": 1.0
}
```

Initial state contains no `wooden pickaxe` and no `cobblestone`.

## Seeded Stage 2 Memory

Before the main run, the test seeds one real successful episode through
`MultimodalMemory.record_success(...)`.

Verified seed result:

- `successful_episode_count == 1`
- `prerequisites_for("cobblestone")` contains
  `wooden pickaxe --(tool, quantity=1)--> cobblestone`

This seed uses the real `DependencyExtractor`; it does not write raw SQL.

## Initial Mine-Step Reliability

The deterministic model-confidence provider always returns:

```json
{
  "confidence": 0.95,
  "reason": "controlled high-confidence response"
}
```

Environment conditions:

- no image
- no image vector
- no image encoder
- no text encoder

Therefore `pE` is explicitly unavailable by design.

For the initial `mine cobblestone` step:

- `pK.available == true`
- `pK.probability == 0.0`
- `pK.hard_conflict == true`
- missing evidence includes:
  - `item = wooden pickaxe`
  - `relation_type = tool`
  - `required = 1.0`
  - `available = 0.0`
- `pL.probability == 0.95`
- `pE.available == false`
- overall `Pi == 0.9306122448979591`

This confirms the intended property: high model confidence does not suppress the
knowledge hard conflict.

## Trigger Observation

Observed trigger invariants from the main run:

- first window step indices: `[0, 1]`
- `hard_conflict == true`
- `low_confidence == true`
- `previous_interval == 3`
- `next_interval == 1`

Post-patch validation also produced a forced one-step window with:

- `forced == true`
- `reason == "post_revision_validation"`

## Evaluation Patch

The deterministic evaluation provider returns one structured patch outcome:

- `accepted = false`
- `request_replan = false`
- one critical `knowledge` issue on the mine step
- one `insert_before` edit targeting the actual mine step ID from the request

Inserted steps:

1. `craft wooden pickaxe`
2. `equip wooden pickaxe`

The provider derives `plan_id`, `plan_version`, and `target_step_id` from the real
prompt payload; it does not hard-code transient IDs.

## Final Plan And Lineage

Verified lineage:

- initial plan version: `1`
- final plan version: `2`
- `final_plan.parent_plan_id == initial_plan.plan_id`
- `final_plan.plan_id != initial_plan.plan_id`
- `revision_count == 1`
- `unresolved == []`

Final action order:

1. `find cobblestone`
2. `craft wooden pickaxe`
3. `equip wooden pickaxe`
4. `mine cobblestone` `times=4`

For the final mine step:

- `pK.available == true`
- `pK.probability == 1.0`
- `pK.hard_conflict == false`

## Stage 6 Result Counts

Main happy-path run counts:

- `success == true`
- `reactive_replan_count == 0`
- `pre_execution_revision_count == 1`
- `evaluation_count == 1`
- `planning_fallback_count == 0`
- `pre_execution_block_count == 0`
- `controller_execution_count == 1`
- `memory_recorded == true`
- `failure_reason == ""`

The controlled Controller verified it received the revised plan, not the original plan:

- received `plan_id == final_plan.plan_id`
- received `version == 2`

## Memory Counts

Verified memory deltas in the happy-path run:

- successful episodes: `1 -> 2`
- scene exemplars for task `cobblestone`: `0 -> 2`
- latest successful episode scene count: `2`

The two stored scenes are:

- initial scene snapshot
- final scene snapshot

## Trace Event Sequence

Observed trace event type sequence in the happy-path run:

1. `planning_started`
2. `reasoning_plan_created`
3. `reliability_window_evaluated`
4. `evaluation_report`
5. `plan_revised`
6. `reliability_window_evaluated`
7. `reliability_window_evaluated`
8. `cognitive_control_complete`
9. `dc3pa_planning_outcome`
10. `plan_ready_for_controller`
11. `controller_completed`
12. `multimodal_memory_recorded`
13. `task_succeeded`

This matches the logical flow required by the controlled test.

## Validation Pass A

Commands:

```bash
cd MP5_agent
python -m compileall dc3pa scripts_dc3pa tests_dc3pa
pytest -q
python scripts_dc3pa/stage6_cobblestone_controlled_test.py --temp-root /tmp/dc3pa_stage6_cobble_a > /tmp/dc3pa_cobble_run_a.json
python -m json.tool /tmp/dc3pa_cobble_run_a.json >/dev/null
```

Results:

- `compileall`: passed
- `pytest -q`: `118 passed in 1.32s`
- script JSON parse: passed

Pass A semantic verification:

- main controlled test payload passed all happy-path assertions
- trace event order matched the expected logical sequence
- successful episodes increased `1 -> 2`
- scene exemplars increased `0 -> 2`

## Validation Pass B

Commands:

```bash
python scripts_dc3pa/stage6_cobblestone_controlled_test.py --temp-root /tmp/dc3pa_stage6_cobble_b > /tmp/dc3pa_cobble_run_b.json
python -m json.tool /tmp/dc3pa_cobble_run_b.json >/dev/null
pytest -q tests_dc3pa/test_stage6_cobblestone_controlled.py
```

Results:

- second script JSON parse: passed
- `pytest -q tests_dc3pa/test_stage6_cobblestone_controlled.py`: `4 passed in 0.23s`

Normalized A/B comparison:

- stable semantic projection: equal
- success state: equal
- counts: equal
- action order: equal
- hard-conflict / trigger invariants: equal
- final inventory: equal
- memory deltas: equal
- event type sequence: equal

## Adversarial Test Results

### 1. Evaluation incorrectly accepts a hard conflict

Scenario: evaluation provider returns `accepted=true` for the original hard conflict.

Verified outcome:

- `success == false`
- unresolved contains `reason == "accepted_despite_hard_conflict"`
- `unresolved_plan_policy == block` blocks execution
- `controller_execution_count == 0`
- `pre_execution_block_count == 1`
- `memory_recorded == false`
- successful episode count stays `1 -> 1`

### 2. Controller success but Goal Check false

Scenario: controlled Controller returns success but does not add `cobblestone`.

Verified outcome:

- `success == false`
- `failure_reason == "goal_not_achieved"`
- `controller_execution_count == 1`
- `memory_recorded == false`
- successful episode count stays `1 -> 1`
- final inventory still has no `cobblestone >= 4`

## Production Code Changes

No production logic was modified for this task.

Only new controlled-test files and audit/report documents were added.

One test-only fix was made during implementation:

- the A/B repeatability normalizer was expanded to remove lineage ID fields such as
  `parent_plan_id` and `previous_plan_id` before stable comparison

This did not affect production behavior.

## Repository Hygiene

Checked commands:

```bash
git status --short
find . -type f \( -name '*.sqlite3' -o -name '*.db' -o -name 'trace.jsonl' \) -print
```

Findings:

- no new SQLite, DB, or trace file was created inside the repository by this task
- reported `.sqlite3` files are pre-existing tracked legacy artifacts outside this diff
- grep scans over the new files found no real key, token, password, or absolute local
  path leak
- the controlled test writes only to temporary directories under `/tmp`

## Real Minecraft Smoke-Test Readiness

This task did not run real Minecraft. It only established an offline controlled
Stage 2-6 closed-loop validation.

Still unverified for a real Minecraft smoke test:

- MineDojo import/runtime availability
- JDK / Minecraft backend availability
- MineLLM service endpoint readiness
- model credential wiring
- legacy Controller low-level environment execution against a real game instance
- real image encoder plugin/checkpoint
- real text encoder plugin/checkpoint

If those dependencies become available, the next step should be a separately authorized
real-environment smoke command, not an automatic continuation of this offline test.

## Conclusion

CONTROLLED_STAGE6_TEST: PASS
