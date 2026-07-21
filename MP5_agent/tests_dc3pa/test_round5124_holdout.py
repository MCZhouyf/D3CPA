from __future__ import annotations

import json
from pathlib import Path

import pytest

from dc3pa.experiments.round5124_holdout import (
    FinalHoldoutRuntimeRelease,
    HoldoutDecisionRecord,
    LockedHoldoutExecutionManifest,
    claim_single_use_ledger_after_asset_preflight,
    claim_single_use_ledger,
    consume_single_use_ledger,
    create_single_use_ledger,
    sha256_file,
)
from dc3pa.experiments.round5124_holdout_features import export_holdout_features
from dc3pa.experiments.task_assets import tree_sha256


def _runtime(
    *,
    candidate_sha: str = "candidate-sha",
    active_manifest_sha: str = "active-manifest",
    runtime_tree_sha: str = "runtime-tree",
    formal_tree_sha: str = "formal-tree",
) -> FinalHoldoutRuntimeRelease:
    return FinalHoldoutRuntimeRelease(
        source_commit="commit",
        controller_sha256="controller",
        structured_actions_sha256="actions",
        run_agent_sha256="agent",
        evaluator_sha256="evaluator",
        stage6_launcher_sha256="stage6",
        holdout_runner_sha256="runner",
        prompt_hash_bundle_id="prompts",
        active_taskset_release_id="taskset",
        active_taskset_manifest_sha256=active_manifest_sha,
        runtime_task_tree_sha256=runtime_tree_sha,
        formal_task_tree_sha256=formal_tree_sha,
        active_task_count=50,
        paper_memory_v5_release_id="memory",
        paper_memory_snapshot_root_sha256="snapshot",
        formal_log_bootstrap_policy_id="bootstrap",
        candidate_artifact_id="candidate",
        candidate_artifact_sha256=candidate_sha,
        activation_policy_id="activation",
        activation_policy_sha256="activation-sha",
        sealed_assignment_sha256="assignments",
        execution_budget={
            "action_step_timeout_seconds": 30,
            "episode_timeout_seconds": 3600,
            "max_execution_attempts": 4,
            "max_explore_steps": 120,
            "max_planning_replans": 4,
            "maximum_technical_retries_per_assignment": 2,
            "provider_maximum_retries": 3,
            "provider_request_timeout_seconds": 180.0,
        },
        scientific_success_logic_sha256="success",
        memory_readonly=True,
        evaluation_chain_enabled=False,
        fusion_affects_action_selection=False,
        formal_memory_writes_permitted=False,
        acquisition_writes_permitted=False,
        controller_changes_after_freeze_permitted=False,
    ).with_id()


def _manifest(assignments: Path, output_root: Path) -> LockedHoldoutExecutionManifest:
    return LockedHoldoutExecutionManifest(
        source_commit="commit",
        runtime_release_id="runtime",
        runtime_release_sha256="runtime-sha",
        candidate_artifact_id="candidate",
        candidate_artifact_sha256="candidate-sha",
        activation_policy_id="activation",
        activation_policy_sha256="activation-sha",
        sealed_assignment_sha256=sha256_file(assignments),
        expected_assignment_count=15,
        output_root=str(output_root),
        github_actions_run_url="https://github.com/example/actions/runs/1",
        source_worktree_clean=True,
        github_actions_green=True,
        holdout_outcome_files_absent=True,
    ).with_id()


def _record(**overrides) -> HoldoutDecisionRecord:
    values = {
        "record_id": "record",
        "collection_id": "collection",
        "development_input_release_id": "input",
        "development_protocol_id": "protocol",
        "role": "dev_holdout",
        "group_id": "group",
        "task": "craft chest",
        "seed": "1",
        "difficulty": "easy",
        "run_id": "run",
        "decision_index": 0,
        "source_commit": "commit",
        "paper_memory_v5_release_id": "memory",
        "snapshot_root_sha256_before": "snapshot",
        "snapshot_root_sha256_after": "snapshot",
        "bootstrap_policy_id": "bootstrap",
        "prompt_hash_bundle_id": "prompts",
        "requested_model_name": "gpt-5.1",
        "returned_model_identities": ("returned",),
        "local_subgoal": "craft chest",
        "proposed_action": "{}",
        "knowledge_hard_feasible": True,
        "knowledge_coverage": 0.8,
        "knowledge_unknown": False,
        "knowledge_missing_prerequisites": (),
        "confidence_level": "high",
        "environment_topk_exemplar_ids": (),
        "environment_topk_similarities": (),
        "environment_compatibility": 0.0,
        "environment_coverage": 0.0,
        "environment_raw_state": "unknown",
        "decision_correct": True,
        "task_completed": True,
        "planner_calls": 1,
        "reflection_calls": 0,
        "evaluation_chain_calls": 0,
        "controller_calls": 1,
        "bootstrap_event_count": 1,
        "injected_log_count": 0,
        "input_tokens": 1,
        "output_tokens": 1,
        "reasoning_tokens": 0,
        "latency_ms": 1.0,
        "formal_memory_write_count": 0,
        "acquisition_write_count": 0,
        "holdout_accessed": True,
        "excluded_from_final_evaluation": False,
    }
    values.update(overrides)
    return HoldoutDecisionRecord(**values).with_hash()


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _active_taskset(tmp_path: Path) -> tuple[Path, FinalHoldoutRuntimeRelease]:
    root = tmp_path / "active"
    task_root = root / "creative_task_jsons"
    formal_root = root / "formal_task_specs"
    task_root.mkdir(parents=True)
    formal_root.mkdir(parents=True)
    artifacts = []
    for index in range(49):
        filename = f"task_{index:02d}.json"
        _write(task_root / filename, [{"task": f"item {index}"}])
        _write(formal_root / filename, {"task_name": f"task {index}"})
    pressure_plate = "craft_wooden_pressure_plate.json"
    _write(task_root / pressure_plate, [{"task": "wooden pressure plate"}])
    _write(
        formal_root / pressure_plate,
        {"task_name": "craft wooden pressure plate"},
    )
    for kind, folder in (
        ("runtime_task_json", "creative_task_jsons"),
        ("formal_task_spec", "formal_task_specs"),
    ):
        for path in sorted((root / folder).glob("*.json")):
            artifacts.append(
                {
                    "artifact_kind": kind,
                    "path": path.relative_to(root).as_posix(),
                }
            )
    manifest = root / "active_artifacts.json"
    _write(manifest, {"artifacts": artifacts})
    runtime = _runtime(
        active_manifest_sha=sha256_file(manifest),
        runtime_tree_sha=tree_sha256(task_root),
        formal_tree_sha=tree_sha256(formal_root),
    )
    return root, runtime


def test_single_use_holdout_ledger_cannot_reopen(tmp_path):
    assignments = tmp_path / "sealed.json"
    assignments.write_text("sealed", encoding="utf-8")
    manifest = _manifest(assignments, tmp_path / "out")
    ledger = tmp_path / "ledger.json"
    create_single_use_ledger(ledger, manifest=manifest)
    claim_single_use_ledger(
        ledger, manifest=manifest, sealed_assignment_path=assignments
    )
    summary = tmp_path / "summary.json"
    summary.write_text("summary", encoding="utf-8")
    consume_single_use_ledger(
        ledger, campaign_summary_sha256=sha256_file(summary)
    )
    with pytest.raises(ValueError, match="already been opened"):
        claim_single_use_ledger(
            ledger, manifest=manifest, sealed_assignment_path=assignments
        )


def test_single_use_holdout_rejects_assignment_drift_before_claim(tmp_path):
    assignments = tmp_path / "sealed.json"
    assignments.write_text("sealed", encoding="utf-8")
    manifest = _manifest(assignments, tmp_path / "out")
    ledger = tmp_path / "ledger.json"
    create_single_use_ledger(ledger, manifest=manifest)
    assignments.write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="assignment hash mismatch"):
        claim_single_use_ledger(
            ledger, manifest=manifest, sealed_assignment_path=assignments
        )
    assert json.loads(ledger.read_text())["state"] == "sealed_unopened"


def test_bad_active_task_root_cannot_claim_holdout_ledger(tmp_path):
    assignments = tmp_path / "sealed.json"
    assignments.write_text("sealed", encoding="utf-8")
    manifest = _manifest(assignments, tmp_path / "out")
    ledger = tmp_path / "ledger.json"
    create_single_use_ledger(ledger, manifest=manifest)
    _, runtime = _active_taskset(tmp_path)
    assignments.unlink()

    with pytest.raises(FileNotFoundError, match="Active taskset root"):
        claim_single_use_ledger_after_asset_preflight(
            ledger,
            manifest=manifest,
            sealed_assignment_path=assignments,
            active_taskset_root=tmp_path / "wrong-root",
            runtime=runtime,
        )

    assert json.loads(ledger.read_text())["state"] == "sealed_unopened"


def test_active_task_preflight_resolves_pressure_plate_pair_before_claim(tmp_path):
    assignments = tmp_path / "sealed.json"
    assignments.write_text("sealed", encoding="utf-8")
    manifest = _manifest(assignments, tmp_path / "out")
    ledger = tmp_path / "ledger.json"
    create_single_use_ledger(ledger, manifest=manifest)
    active_root, runtime = _active_taskset(tmp_path)

    _, roots = claim_single_use_ledger_after_asset_preflight(
        ledger,
        manifest=manifest,
        sealed_assignment_path=assignments,
        active_taskset_root=active_root,
        runtime=runtime,
    )

    assert (roots["task_root"] / "craft_wooden_pressure_plate.json").is_file()
    assert (
        roots["formal_task_spec_root"] / "craft_wooden_pressure_plate.json"
    ).is_file()
    assert json.loads(ledger.read_text())["state"] == "claimed"


def test_holdout_record_rejects_evaluation_or_writes():
    with pytest.raises(ValueError, match="Evaluation Chain"):
        _record(evaluation_chain_calls=1)
    with pytest.raises(ValueError, match="protected write"):
        _record(formal_memory_write_count=1)


def test_candidate_is_immutable_after_runtime_freeze(tmp_path):
    candidate = tmp_path / "candidate.json"
    _write(candidate, {"artifact_id": "candidate"})
    runtime = _runtime(candidate_sha=sha256_file(candidate))
    runtime_path = tmp_path / "runtime.json"
    _write(runtime_path, runtime.to_dict())
    decisions = tmp_path / "decisions.jsonl"
    decisions.write_text(json.dumps(_record().to_dict()) + "\n", encoding="utf-8")
    confidence = tmp_path / "confidence.json"
    _write(
        confidence,
        {
            "release_id": "confidence",
            "levels": [{"level": "high", "calibrated_probability": 0.8}],
        },
    )
    environment = tmp_path / "environment.json"
    _write(
        environment,
        {
            "release_id": "environment",
            "selected_result": {
                "candidate": {
                    "minimum_similarity": 0.4,
                    "minimum_coverage": 0.5,
                    "match_compatibility_threshold": 0.5,
                    "mismatch_compatibility_threshold": 0.45,
                },
                "state_probabilities": {
                    "matched": 0.8,
                    "mismatch": 0.2,
                    "unknown": 0.5,
                },
            },
        },
    )
    _write(candidate, {"artifact_id": "candidate", "tampered": True})
    with pytest.raises(ValueError, match="Candidate changed"):
        export_holdout_features(
            decisions_path=decisions,
            confidence_release_path=confidence,
            environment_release_path=environment,
            candidate_path=candidate,
            runtime_release_path=runtime_path,
            output_path=tmp_path / "features.jsonl",
        )


def test_locked_evaluator_is_physically_separate_from_fitter():
    source = (
        Path(__file__).parents[1]
        / "dc3pa"
        / "experiments"
        / "round5124_holdout_evaluator.py"
    ).read_text(encoding="utf-8")
    assert "round5124_fusion_fit" not in source
    assert "fit_candidate" not in source
    assert "optimizer" not in source.lower()
