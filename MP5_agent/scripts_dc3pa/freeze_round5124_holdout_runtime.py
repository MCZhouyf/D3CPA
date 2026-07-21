#!/usr/bin/env python3
"""Freeze the final runtime and sealed-unopened Round 5.12.4 holdout lock."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.bootstrap_data_guard import BootstrapDataBinding
from dc3pa.experiments.round5124_holdout import (
    FinalHoldoutRuntimeRelease,
    LockedHoldoutExecutionManifest,
    create_single_use_ledger,
    preflight_active_task_assets,
    sha256_file,
)
from dc3pa.experiments.round5124_fusion_fit import (
    MonotonicFusionCandidateArtifact,
    Round5124ActivationPolicy,
)
from dc3pa.experiments.task_assets import tree_sha256


def _load(path: Path):
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _serialized_sha256(payload) -> str:
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _required_protocol_id(protocol) -> str:
    value = protocol.get("protocol_id") or protocol.get("development_protocol_id")
    if not value:
        raise ValueError("Development protocol has no frozen protocol ID")
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--activation-policy", required=True, type=Path)
    parser.add_argument("--sealed-assignments", required=True, type=Path)
    parser.add_argument("--active-taskset-release", required=True, type=Path)
    parser.add_argument("--active-taskset-root", required=True, type=Path)
    parser.add_argument("--bootstrap-policy", required=True, type=Path)
    parser.add_argument("--bootstrap-amendment", required=True, type=Path)
    parser.add_argument("--development-protocol", required=True, type=Path)
    parser.add_argument("--memory-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--github-actions-run-url", required=True)
    parser.add_argument("--github-actions-conclusion", required=True)
    parser.add_argument("--runtime-output", required=True, type=Path)
    parser.add_argument("--manifest-output", required=True, type=Path)
    parser.add_argument("--ledger-output", required=True, type=Path)
    parser.add_argument("--bootstrap-binding-output", required=True, type=Path)
    args = parser.parse_args()

    source_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip():
        raise ValueError("Source worktree must be clean before holdout freeze")
    if args.github_actions_conclusion != "success":
        raise ValueError("GitHub Actions must be green before holdout freeze")
    if args.output_root.exists() and any(args.output_root.iterdir()):
        raise ValueError("Holdout output root already contains outcome files")

    candidate_payload = _load(args.candidate)
    candidate_payload["feature_order"] = tuple(candidate_payload["feature_order"])
    candidate = MonotonicFusionCandidateArtifact(**candidate_payload)
    activation_payload = _load(args.activation_policy)
    activation_payload["primary_metrics"] = tuple(activation_payload["primary_metrics"])
    activation_payload["calibration_metrics"] = tuple(activation_payload["calibration_metrics"])
    activation = Round5124ActivationPolicy(**activation_payload)
    taskset = _load(args.active_taskset_release)
    active_taskset_root = args.active_taskset_root.resolve()
    if args.active_taskset_release.resolve().parent != active_taskset_root:
        raise ValueError("Active taskset release must be inside active taskset root")
    active_manifest = active_taskset_root / "active_artifacts.json"
    runtime_task_root = active_taskset_root / "creative_task_jsons"
    formal_task_root = active_taskset_root / "formal_task_specs"
    if not all(
        path.is_file() for path in (active_manifest, args.active_taskset_release)
    ):
        raise FileNotFoundError("Active taskset release or manifest is missing")
    if not all(path.is_dir() for path in (runtime_task_root, formal_task_root)):
        raise FileNotFoundError("Active runtime/formal task asset directory is missing")
    bootstrap = _load(args.bootstrap_policy)
    amendment = _load(args.bootstrap_amendment)
    protocol = _load(args.development_protocol)
    protocol_id = _required_protocol_id(protocol)
    output_paths = (
        args.runtime_output,
        args.manifest_output,
        args.ledger_output,
        args.bootstrap_binding_output,
    )
    existing_outputs = [str(path) for path in output_paths if path.exists()]
    if existing_outputs:
        raise FileExistsError(
            "Holdout freeze output already exists: " + ", ".join(existing_outputs)
        )
    snapshot = _load(args.memory_root / "snapshot_manifest.json")
    paths = {
        "controller": ROOT / "agent" / "controller.py",
        "structured_actions": ROOT / "agent" / "structured_actions.py",
        "run_agent": ROOT / "agent" / "run_agent.py",
        "stage6": ROOT / "scripts_dc3pa" / "stage6_run_minecraft.py",
        "runner": ROOT / "scripts_dc3pa" / "run_round5124_holdout_campaign.py",
    }
    runtime = FinalHoldoutRuntimeRelease(
        source_commit=source_commit,
        controller_sha256=sha256_file(paths["controller"]),
        structured_actions_sha256=sha256_file(paths["structured_actions"]),
        run_agent_sha256=sha256_file(paths["run_agent"]),
        evaluator_sha256=sha256_file(paths["run_agent"]),
        stage6_launcher_sha256=sha256_file(paths["stage6"]),
        holdout_runner_sha256=sha256_file(paths["runner"]),
        prompt_hash_bundle_id="e8703f9d7a79612afa6a58ce37dca2f6e8591b943f5dd8c6ece9b89f9d45bd00",
        active_taskset_release_id=str(taskset["release_id"]),
        active_taskset_manifest_sha256=sha256_file(active_manifest),
        runtime_task_tree_sha256=tree_sha256(runtime_task_root),
        formal_task_tree_sha256=tree_sha256(formal_task_root),
        active_task_count=int(taskset["active_task_count"]),
        paper_memory_v5_release_id="cc2310aeb60f63e6a1896a4c05109a1ec391649ce102e11b65b6343605789813",
        paper_memory_snapshot_root_sha256=str(snapshot["snapshot_root_sha256"]),
        formal_log_bootstrap_policy_id=str(bootstrap["policy_id"]),
        candidate_artifact_id=candidate.artifact_id,
        candidate_artifact_sha256=sha256_file(args.candidate),
        activation_policy_id=activation.policy_id,
        activation_policy_sha256=sha256_file(args.activation_policy),
        sealed_assignment_sha256=sha256_file(args.sealed_assignments),
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
        scientific_success_logic_sha256=sha256_file(paths["run_agent"]),
        memory_readonly=True,
        evaluation_chain_enabled=False,
        fusion_affects_action_selection=False,
        formal_memory_writes_permitted=False,
        acquisition_writes_permitted=False,
        controller_changes_after_freeze_permitted=False,
    ).with_id()
    preflight_active_task_assets(active_taskset_root, runtime=runtime)
    runtime_payload = runtime.to_dict()
    manifest = LockedHoldoutExecutionManifest(
        source_commit=source_commit,
        runtime_release_id=runtime.release_id,
        runtime_release_sha256=_serialized_sha256(runtime_payload),
        candidate_artifact_id=candidate.artifact_id,
        candidate_artifact_sha256=sha256_file(args.candidate),
        activation_policy_id=activation.policy_id,
        activation_policy_sha256=sha256_file(args.activation_policy),
        sealed_assignment_sha256=sha256_file(args.sealed_assignments),
        expected_assignment_count=15,
        output_root=str(args.output_root.resolve()),
        github_actions_run_url=args.github_actions_run_url,
        source_worktree_clean=True,
        github_actions_green=True,
        holdout_outcome_files_absent=True,
    ).with_id()
    binding = BootstrapDataBinding(
        binding_name="dc3pa-round5124-dev-holdout-v1",
        bootstrap_policy_id=str(bootstrap["policy_id"]),
        bootstrap_amendment_id=str(amendment["amendment_id"]),
        source_commit=source_commit,
        blueprint_id=protocol_id,
        scope="dev_holdout",
        method_id="single_chain_reactive_development",
        task_catalog_sha256=str(taskset["catalog_sha256"]),
        prompt_hash_bundle_id=runtime.prompt_hash_bundle_id,
        controller_identity_sha256=runtime.controller_sha256,
        evaluator_identity_sha256=runtime.evaluator_sha256,
        memory_snapshot_id=runtime.paper_memory_v5_release_id,
        memory_snapshot_sha256=runtime.paper_memory_snapshot_root_sha256,
    ).with_id()
    _write(args.runtime_output, runtime_payload)
    _write(args.manifest_output, manifest.to_dict())
    _write(args.bootstrap_binding_output, binding.to_dict())
    # The single-use ledger is created last, after every other freeze artifact.
    create_single_use_ledger(args.ledger_output, manifest=manifest)
    print(
        json.dumps(
            {
                "runtime_release_id": runtime.release_id,
                "execution_manifest_id": manifest.manifest_id,
                "bootstrap_binding_id": binding.binding_id,
                "ledger_state": "sealed_unopened",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
