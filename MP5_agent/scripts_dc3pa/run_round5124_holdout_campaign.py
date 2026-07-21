#!/usr/bin/env python3
"""Execute the sealed Round 5.12.4 development holdout exactly once."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.bootstrap_data_guard import load_bootstrap_data_binding
from dc3pa.experiments.formal_acquisition_execution import TECHNICAL_FAILURE_CATEGORIES
from dc3pa.experiments.round511_remediation import classify_failure_at_source
from dc3pa.experiments.round5124_holdout import (
    FinalHoldoutRuntimeRelease,
    LockedHoldoutExecutionManifest,
    claim_single_use_ledger_after_asset_preflight,
    consume_single_use_ledger,
    sha256_file,
)
from dc3pa.experiments.round5124_holdout_features import export_holdout_features
from scripts_dc3pa.run_round511_development_campaign import (
    _formal_task_spec_path,
    _load,
    _run_stage6_process,
    _stage6_environment,
    _task_path,
    _write_exclusive,
)


MAX_TECHNICAL_RETRIES = 2


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _load_runtime(path: Path) -> FinalHoldoutRuntimeRelease:
    return FinalHoldoutRuntimeRelease(**_load(path))


def _load_manifest(path: Path) -> LockedHoldoutExecutionManifest:
    return LockedHoldoutExecutionManifest(**_load(path))


def _validate_assignments(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    assignments = payload.get("assignments")
    if not isinstance(assignments, list) or len(assignments) != 15:
        raise ValueError("Locked development holdout must contain exactly 15 assignments")
    seen_groups = set()
    seen_pairs = set()
    validated = []
    for item in assignments:
        if not isinstance(item, Mapping):
            raise ValueError("Locked holdout assignment is not an object")
        if item.get("role") != "dev_holdout":
            raise ValueError("Locked holdout contains a non-holdout assignment")
        task = str(item.get("task", ""))
        seed = str(item.get("seed", ""))
        group_id = str(item.get("group_id", ""))
        difficulty = str(item.get("difficulty", ""))
        if not all((task, seed, group_id, difficulty)):
            raise ValueError("Locked holdout assignment identity is incomplete")
        if task == "mine sand":
            raise ValueError("Locked holdout contains superseded mine sand")
        if group_id in seen_groups or (task, seed) in seen_pairs:
            raise ValueError("Locked holdout assignments are not unique")
        seen_groups.add(group_id)
        seen_pairs.add((task, seed))
        validated.append(item)
    return sorted(validated, key=lambda item: int(item["sequence_index"]))


def _verify_runtime(
    *,
    runtime: FinalHoldoutRuntimeRelease,
    runtime_path: Path,
    manifest: LockedHoldoutExecutionManifest,
    candidate_path: Path,
    activation_policy_path: Path,
    output_root: Path,
) -> str:
    current_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if current_commit != runtime.source_commit or current_commit != manifest.source_commit:
        raise ValueError("Current source commit differs from frozen holdout runtime")
    if subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip():
        raise ValueError("Source worktree must remain clean during holdout")
    paths = {
        "controller_sha256": ROOT / "agent" / "controller.py",
        "structured_actions_sha256": ROOT / "agent" / "structured_actions.py",
        "run_agent_sha256": ROOT / "agent" / "run_agent.py",
        "evaluator_sha256": ROOT / "agent" / "run_agent.py",
        "stage6_launcher_sha256": ROOT / "scripts_dc3pa" / "stage6_run_minecraft.py",
        "holdout_runner_sha256": Path(__file__).resolve(),
    }
    for field, path in paths.items():
        if sha256_file(path) != getattr(runtime, field):
            raise ValueError(f"Frozen holdout runtime file changed: {field}")
    checks = (
        (sha256_file(runtime_path), manifest.runtime_release_sha256),
        (runtime.release_id, manifest.runtime_release_id),
        (sha256_file(candidate_path), runtime.candidate_artifact_sha256),
        (sha256_file(candidate_path), manifest.candidate_artifact_sha256),
        (sha256_file(activation_policy_path), runtime.activation_policy_sha256),
        (sha256_file(activation_policy_path), manifest.activation_policy_sha256),
        (str(output_root.resolve()), manifest.output_root),
    )
    if any(actual != expected for actual, expected in checks):
        raise ValueError("Frozen holdout runtime/manifest artifact binding changed")
    return current_commit


def _command(
    args: argparse.Namespace,
    *,
    assignment: Mapping[str, Any],
    binding: Path,
    records: Path,
    trace: Path,
    receipt: Path,
    bootstrap_output: Path,
    task_root: Path,
    formal_task_spec_root: Path,
) -> list[str]:
    return [
        "xvfb-run",
        "-a",
        "-s",
        "-screen 0 1920x1080x24",
        str(args.python),
        str(ROOT / "scripts_dc3pa" / "stage6_run_minecraft.py"),
        "--mode",
        "reasoning_only",
        "--model-profile",
        "gpt51_reference",
        "--provider-model-alias-policy",
        str(args.provider_model_alias_policy),
        "--provider-model-alias-approval",
        str(args.provider_model_alias_approval),
        "--mllm_url",
        os.environ.get("OPENAI_BASE_URL", ""),
        "--task",
        str(_task_path(task_root, str(assignment["task"]))),
        "--formal-task-spec",
        str(_formal_task_spec_path(formal_task_spec_root, str(assignment["task"]))),
        "--config",
        str(args.stage6_config),
        "--memory-root",
        str(args.memory_root),
        "--trace",
        str(trace),
        "--max-execution-attempts",
        "4",
        "--image-encoder-factory",
        "dc3pa.memory.mineclip_scene_encoder:build_mineclip_image_encoder",
        "--text-encoder-factory",
        "dc3pa.memory.mineclip_scene_encoder:build_mineclip_text_encoder",
        "--encoder-config-json",
        json.dumps(
            {
                "image": {"checkpoint_path": str(args.mineclip_checkpoint), "device": args.mineclip_device},
                "text": {"checkpoint_path": str(args.mineclip_checkpoint), "device": args.mineclip_device},
            },
            sort_keys=True,
        ),
        "--require-environment-score",
        "--real-experiment-phase",
        "development_data_validated",
        "--real-experiment-task",
        str(assignment["task"]),
        "--real-experiment-seed",
        str(assignment["seed"]),
        "--formal-log-bootstrap-policy",
        str(args.bootstrap_policy),
        "--formal-bootstrap-amendment",
        str(args.bootstrap_amendment),
        "--formal-bootstrap-data-binding",
        str(args.bootstrap_binding),
        "--formal-bootstrap-scope",
        "dev_holdout",
        "--formal-bootstrap-method-id",
        "single_chain_reactive_development",
        "--formal-bootstrap-output-root",
        str(bootstrap_output),
        "--formal-bootstrap-receipt",
        str(receipt),
        "--round5124-holdout-run",
        str(binding),
        "--round5124-holdout-records",
        str(records),
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    for name in (
        "assignments",
        "runtime-release",
        "execution-manifest",
        "single-use-ledger",
        "candidate",
        "activation-policy",
        "confidence-release",
        "environment-release",
        "bootstrap-policy",
        "bootstrap-amendment",
        "bootstrap-binding",
        "memory-root",
        "mineclip-checkpoint",
        "active-taskset-root",
        "provider-model-alias-policy",
        "provider-model-alias-approval",
        "output-root",
    ):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument(
        "--stage6-config",
        type=Path,
        default=ROOT / "dc3pa" / "configs" / "stage6_closed_loop.json",
    )
    parser.add_argument("--python", type=Path, default=Path(sys.executable).resolve())
    parser.add_argument("--mineclip-device", default="cuda")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    runtime = _load_runtime(args.runtime_release)
    manifest = _load_manifest(args.execution_manifest)
    current_commit = _verify_runtime(
        runtime=runtime,
        runtime_path=args.runtime_release,
        manifest=manifest,
        candidate_path=args.candidate,
        activation_policy_path=args.activation_policy,
        output_root=args.output_root,
    )
    if not os.environ.get("OPENAI_API_KEY") or not os.environ.get("OPENAI_BASE_URL"):
        raise ValueError("OPENAI_API_KEY and OPENAI_BASE_URL are required")
    bootstrap_binding = load_bootstrap_data_binding(args.bootstrap_binding)
    if (
        bootstrap_binding.scope != "dev_holdout"
        or bootstrap_binding.source_commit != current_commit
        or bootstrap_binding.bootstrap_policy_id != runtime.formal_log_bootstrap_policy_id
        or bootstrap_binding.controller_identity_sha256 != runtime.controller_sha256
        or bootstrap_binding.evaluator_identity_sha256 != runtime.evaluator_sha256
    ):
        raise ValueError("Holdout bootstrap binding differs from frozen runtime")

    # Public task assets are fully checked before this opens the sealed assignments.
    _, asset_roots = claim_single_use_ledger_after_asset_preflight(
        args.single_use_ledger,
        manifest=manifest,
        sealed_assignment_path=args.assignments,
        active_taskset_root=args.active_taskset_root,
        runtime=runtime,
    )
    assignments = _validate_assignments(_load(args.assignments))
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    accepted_records: list[Path] = []
    outcomes = []
    technical_retry_count = 0
    collection_id = "round5124-holdout-" + manifest.manifest_id[:24]

    for assignment in assignments:
        group_root = output_root / "runs" / _sha(str(assignment["group_id"]))[:16]
        group_root.mkdir(parents=True, exist_ok=False)
        accepted = False
        for attempt in range(MAX_TECHNICAL_RETRIES + 1):
            attempt_root = group_root / f"attempt-{attempt}"
            attempt_root.mkdir()
            trace = attempt_root / "trace.jsonl"
            records = attempt_root / "holdout_decisions.jsonl"
            receipt = attempt_root / "bootstrap_receipt.json"
            console = attempt_root / "console.log"
            run_id = "r5124h-" + _sha(
                {"manifest": manifest.manifest_id, "group": assignment["group_id"], "attempt": attempt}
            )[:24]
            binding_path = attempt_root / "run_binding.json"
            _write_exclusive(
                binding_path,
                {
                    "collection_id": collection_id,
                    "development_input_release_id": "bd2f2e96e3e0fd3e4c8dcf4b2180d15adf971d44181ae51bb84c932af0533f99",
                    "development_protocol_id": bootstrap_binding.blueprint_id,
                    "role": "dev_holdout",
                    "group_id": assignment["group_id"],
                    "task": assignment["task"],
                    "seed": str(assignment["seed"]),
                    "difficulty": assignment["difficulty"],
                    "run_id": run_id,
                    "source_commit": current_commit,
                    "paper_memory_v5_release_id": runtime.paper_memory_v5_release_id,
                    "snapshot_root_sha256": runtime.paper_memory_snapshot_root_sha256,
                    "bootstrap_policy_id": runtime.formal_log_bootstrap_policy_id,
                    "prompt_hash_bundle_id": runtime.prompt_hash_bundle_id,
                    "requested_model_name": "gpt-5.1",
                    "final_holdout_runtime_release_id": runtime.release_id,
                    "locked_holdout_execution_manifest_id": manifest.manifest_id,
                },
            )
            command = _command(
                args,
                assignment=assignment,
                binding=binding_path,
                records=records,
                trace=trace,
                receipt=receipt,
                bootstrap_output=attempt_root / "bootstrap",
                task_root=asset_roots["task_root"],
                formal_task_spec_root=asset_roots["formal_task_spec_root"],
            )
            env = _stage6_environment(seed=assignment["seed"], max_explore_steps=120)
            with console.open("ab") as handle:
                return_code = _run_stage6_process(
                    command,
                    cwd=ROOT,
                    env=env,
                    output=handle,
                    timeout_seconds=3600,
                )
            receipt_payload = _load(receipt) if receipt.is_file() else {}
            if bool(receipt_payload.get("pipeline_pass")) and records.is_file():
                accepted_records.append(records)
                outcomes.append(
                    {
                        "group_id": assignment["group_id"],
                        "task_completed": bool(receipt_payload.get("task_completed")),
                        "attempt": attempt,
                    }
                )
                accepted = True
                break
            category, signal = classify_failure_at_source(
                return_code=return_code, trace_path=trace
            )
            _write_exclusive(
                attempt_root / "technical_failure.json",
                {"category": category or "unclassifiable", "signal": dict(signal)},
            )
            if category not in TECHNICAL_FAILURE_CATEGORIES:
                raise RuntimeError(f"Unclassifiable holdout technical failure: {category}")
            if attempt < MAX_TECHNICAL_RETRIES:
                technical_retry_count += 1
        if not accepted:
            raise RuntimeError(
                f"Holdout assignment exhausted {MAX_TECHNICAL_RETRIES} technical retries"
            )

    decision_output = output_root / "holdout_decisions.jsonl"
    with decision_output.open("x", encoding="utf-8") as handle:
        for path in accepted_records:
            handle.write(path.read_text(encoding="utf-8"))
    feature_output = output_root / "holdout_fusion_features.jsonl"
    feature_summary = export_holdout_features(
        decisions_path=decision_output,
        confidence_release_path=args.confidence_release,
        environment_release_path=args.environment_release,
        candidate_path=args.candidate,
        runtime_release_path=args.runtime_release,
        output_path=feature_output,
    )
    summary = {
        "schema_version": 1,
        "collection_id": collection_id,
        "runtime_release_id": runtime.release_id,
        "execution_manifest_id": manifest.manifest_id,
        "assignment_count": len(assignments),
        "scientific_success_count": sum(item["task_completed"] for item in outcomes),
        "scientific_failure_count": sum(not item["task_completed"] for item in outcomes),
        "technical_retry_count": technical_retry_count,
        "decision_count": feature_summary["record_count"],
        "decision_dataset_sha256": sha256_file(decision_output),
        "feature_dataset_sha256": sha256_file(feature_output),
        "formal_memory_write_count": 0,
        "acquisition_write_count": 0,
        "evaluation_chain_call_count": 0,
        "candidate_shadow_only": True,
        "final_evaluation_opened": False,
    }
    summary["summary_id"] = _sha(summary)
    summary_path = output_root / "campaign_summary.json"
    _write_exclusive(summary_path, summary)
    consume_single_use_ledger(
        args.single_use_ledger,
        campaign_summary_sha256=sha256_file(summary_path),
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
