#!/usr/bin/env python3
"""Retry 60-step scientific failures, then continue pending units at 120 steps."""

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

from dc3pa.experiments.formal_acquisition_execution import TECHNICAL_FAILURE_CATEGORIES
from dc3pa.experiments.round511_reconciliation import Round511ReconciliationPolicy
from dc3pa.experiments.round511_remediation import (
    classify_failure_at_source,
    materialize_accepted_datasets,
    next_attempt_index,
    recover_accepted_marker,
)
from dc3pa.experiments.round5122_explore120 import (
    AMENDED_MAX_EXPLORE_STEPS,
    Explore120BudgetContract,
    Explore120ContinuationApproval,
    continuation_queue,
    initialize_continuation_root,
    load_json,
    original_result_map,
    persist_budget,
    validate_contracts,
    write_effective_outputs,
)
from dc3pa.experiments.round5122_pathb import (
    ACTIVE_TASKSET_RELEASE_ID,
    ANALYSIS_POLICY_ID,
    BOOTSTRAP_AMENDMENT_ID,
    BOOTSTRAP_POLICY_ID,
    DEVELOPMENT_INPUT_RELEASE_ID,
    DEVELOPMENT_PROTOCOL_ID,
    FRESH_CAMPAIGN_INPUT_MANIFEST,
    PAPER_MEMORY_SNAPSHOT_ROOT,
    PAPER_MEMORY_V5_RELEASE_ID,
    PROMPT_HASH_BUNDLE_ID,
)
from scripts_dc3pa.run_round511_development_campaign import (
    _load_existing_attempt_summary,
    _run_stage6_process,
    _stage6_command,
    _stage6_environment,
    _validate_assignments,
    _write_exclusive,
)


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _run_id(continuation_id: str, group_id: str, attempt: int) -> str:
    return "r5122x-" + _sha(
        {"continuation_id": continuation_id, "group_id": group_id, "attempt": attempt}
    )[:22]


def _continuation_result_map(root: Path) -> dict[str, Mapping[str, Any]]:
    results = {}
    for marker_path in (root / "runs").glob("*/accepted.json"):
        marker = load_json(marker_path)
        group_id = str(marker.get("group_id", ""))
        if not group_id or group_id in results:
            raise ValueError("Continuation accepted ledger is invalid")
        results[group_id] = marker
    return results


def _prelaunch_gate(
    *,
    assignment: Mapping[str, Any],
    queue_item: Mapping[str, Any],
    approval: Explore120ContinuationApproval,
    budget: Explore120BudgetContract,
    group_root: Path,
    attempt: int,
    budget_path: Path,
) -> None:
    current = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if current != approval.source_commit or current != budget.source_commit:
        raise ValueError("Continuation source changed before MineDojo launch")
    if dict(queue_item["assignment"]) != dict(assignment):
        raise ValueError("Continuation assignment differs from the frozen queue")
    if load_json(budget_path) != budget.to_dict():
        raise ValueError("120-step budget snapshot is missing or mismatched")
    authoritative = next_attempt_index(group_root)
    if authoritative is None or authoritative != attempt:
        raise ValueError("Continuation attempt index is not authorized")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assignments", required=True, type=Path)
    parser.add_argument("--original-campaign-root", required=True, type=Path)
    parser.add_argument("--continuation-approval", required=True, type=Path)
    parser.add_argument("--amended-budget-contract", required=True, type=Path)
    parser.add_argument("--development-input-release", required=True, type=Path)
    parser.add_argument("--bootstrap-policy", required=True, type=Path)
    parser.add_argument("--bootstrap-amendment", required=True, type=Path)
    parser.add_argument("--bootstrap-binding-train", required=True, type=Path)
    parser.add_argument("--bootstrap-binding-tune", required=True, type=Path)
    parser.add_argument("--memory-root", required=True, type=Path)
    parser.add_argument("--mineclip-checkpoint", required=True, type=Path)
    parser.add_argument("--task-root", required=True, type=Path)
    parser.add_argument("--formal-task-spec-root", required=True, type=Path)
    parser.add_argument("--provider-model-alias-policy", required=True, type=Path)
    parser.add_argument("--provider-model-alias-approval", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
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
    if not os.environ.get("OPENAI_API_KEY") or not os.environ.get("OPENAI_BASE_URL"):
        raise ValueError("Provider credentials are required in process environment")
    assignments = _validate_assignments(load_json(args.assignments))
    release = load_json(args.development_input_release)
    protected_release_fields = {
        "release_id": DEVELOPMENT_INPUT_RELEASE_ID,
        "development_protocol_id": DEVELOPMENT_PROTOCOL_ID,
        "active_taskset_release_id": ACTIVE_TASKSET_RELEASE_ID,
        "paper_memory_v5_release_id": PAPER_MEMORY_V5_RELEASE_ID,
        "paper_memory_snapshot_root_sha256": PAPER_MEMORY_SNAPSHOT_ROOT,
        "prompt_hash_bundle_id": PROMPT_HASH_BUNDLE_ID,
        "analysis_policy_id": ANALYSIS_POLICY_ID,
        "formal_bootstrap_policy_id": BOOTSTRAP_POLICY_ID,
        "formal_bootstrap_amendment_id": BOOTSTRAP_AMENDMENT_ID,
    }
    if not bool(release.get("eligible")):
        raise ValueError("Development Input Release is not eligible")
    for field_name, expected in protected_release_fields.items():
        if release.get(field_name) != expected:
            raise ValueError(f"Protected input release changed: {field_name}")
    original_root = args.original_campaign_root.resolve()
    original_manifest = load_json(original_root / FRESH_CAMPAIGN_INPUT_MANIFEST)
    current_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    budget = Explore120BudgetContract.from_mapping(
        load_json(args.amended_budget_contract)
    ).with_id()
    approval = Explore120ContinuationApproval.from_mapping(
        load_json(args.continuation_approval)
    ).with_id()
    validate_contracts(
        approval=approval,
        budget=budget,
        source_commit=current_commit,
        original_manifest=original_manifest,
        assignments=assignments,
    )
    original_results = original_result_map(original_root, assignments)
    queue = continuation_queue(assignments, original_results)
    output_root = args.output_root.resolve()
    manifest_path = initialize_continuation_root(
        output_root=output_root,
        approval=approval,
        budget=budget,
        original_root=original_root,
        original_results=original_results,
        queue=queue,
    )
    manifest = load_json(manifest_path)
    reconciliation_policy = Round511ReconciliationPolicy().with_id()

    for queue_item in queue:
        assignment = queue_item["assignment"]
        group_hash = hashlib.sha256(
            str(assignment["group_id"]).encode("utf-8")
        ).hexdigest()[:16]
        group_root = output_root / "runs" / group_hash
        group_root.mkdir(parents=True, exist_ok=True)
        recover_accepted_marker(output_root, group_root)
        if (group_root / "accepted.json").is_file():
            continue
        while True:
            try:
                attempt = next_attempt_index(group_root)
            except (RuntimeError, ValueError) as exc:
                print(json.dumps({"status": "retry_exhausted", "reason": str(exc)}))
                return 2
            if attempt is None:
                break
            run_id = _run_id(
                str(manifest["continuation_id"]), str(assignment["group_id"]), attempt
            )
            attempt_root = group_root / f"attempt-{attempt}"
            attempt_root.mkdir(parents=True, exist_ok=True)
            summary_path = attempt_root / "attempt_summary.json"
            if _load_existing_attempt_summary(
                summary_path, run_id=run_id, attempt=attempt
            ) is not None:
                continue
            binding = attempt_root / "run_binding.json"
            records = attempt_root / "development_decisions.jsonl"
            trace = attempt_root / "trace.jsonl"
            receipt = attempt_root / "bootstrap_receipt.json"
            console = attempt_root / "console.log"
            bootstrap = attempt_root / "bootstrap"
            budget_path = attempt_root / "execution_budget_snapshot.json"
            persist_budget(budget_path, budget)
            if not binding.exists():
                _write_exclusive(
                    binding,
                    {
                        "collection_id": manifest["continuation_id"],
                        "continuation_approval_id": approval.approval_id,
                        "original_campaign_id": approval.original_campaign_id,
                        "continuation_reason": queue_item["reason"],
                        "development_input_release_id": release["release_id"],
                        "development_protocol_id": release["development_protocol_id"],
                        "role": assignment["role"],
                        "group_id": assignment["group_id"],
                        "task": assignment["task"],
                        "seed": str(assignment["seed"]),
                        "difficulty": assignment["difficulty"],
                        "sequence_index": int(assignment["sequence_index"]),
                        "run_id": run_id,
                        "source_commit": current_commit,
                        "paper_memory_v5_release_id": release[
                            "paper_memory_v5_release_id"
                        ],
                        "snapshot_root_sha256": release[
                            "paper_memory_snapshot_root_sha256"
                        ],
                        "bootstrap_policy_id": release[
                            "formal_bootstrap_policy_id"
                        ],
                        "prompt_hash_bundle_id": release["prompt_hash_bundle_id"],
                        "requested_model_name": "gpt-5.1",
                        "execution_budget_snapshot_id": budget.contract_id,
                    },
                )
            command = _stage6_command(
                args=args,
                assignment=assignment,
                run_binding=binding,
                records=records,
                trace=trace,
                receipt=receipt,
                bootstrap_output=bootstrap,
            )
            env = _stage6_environment(
                seed=assignment["seed"], max_explore_steps=AMENDED_MAX_EXPLORE_STEPS
            )
            _prelaunch_gate(
                assignment=assignment,
                queue_item=queue_item,
                approval=approval,
                budget=budget,
                group_root=group_root,
                attempt=attempt,
                budget_path=budget_path,
            )
            with console.open("ab") as handle:
                returncode = _run_stage6_process(
                    command,
                    cwd=ROOT,
                    env=env,
                    output=handle,
                    timeout_seconds=budget.episode_timeout_seconds,
                )
            receipt_payload = load_json(receipt) if receipt.is_file() else {}
            accepted = bool(receipt_payload.get("pipeline_pass") and records.is_file())
            failure_category = None
            failure_signal: Mapping[str, Any] = {}
            if not accepted:
                failure_category, failure_signal = classify_failure_at_source(
                    return_code=returncode, trace_path=trace
                )
            status = (
                "completed_success"
                if accepted and bool(receipt_payload.get("task_completed"))
                else "completed_scientific_failure"
                if accepted
                else "technical_failure"
            )
            _write_exclusive(
                summary_path,
                {
                    "run_id": run_id,
                    "attempt": attempt,
                    "process_return_code": returncode,
                    "pipeline_pass": bool(receipt_payload.get("pipeline_pass")),
                    "task_completed": bool(receipt_payload.get("task_completed")),
                    "records_present": records.is_file(),
                    "accepted": accepted,
                    "status": status,
                    "failure_category": None if accepted else failure_category or "unclassifiable",
                    "structured_failure_signal": dict(failure_signal),
                    "classification_policy_id": reconciliation_policy.policy_id,
                    "execution_budget_snapshot_id": budget.contract_id,
                    "continuation_reason": queue_item["reason"],
                },
            )
            if accepted:
                recover_accepted_marker(output_root, group_root)
                materialize_accepted_datasets(output_root)
                continuation_results = _continuation_result_map(output_root)
                write_effective_outputs(
                    output_root=output_root,
                    original_root=original_root,
                    assignments=assignments,
                    original_results=original_results,
                    continuation_results=continuation_results,
                )
                break
            if failure_category not in TECHNICAL_FAILURE_CATEGORIES:
                return 2

    continuation_results = _continuation_result_map(output_root)
    effective = write_effective_outputs(
        output_root=output_root,
        original_root=original_root,
        assignments=assignments,
        original_results=original_results,
        continuation_results=continuation_results,
    )
    print(json.dumps(effective, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
