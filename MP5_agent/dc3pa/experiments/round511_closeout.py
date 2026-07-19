"""Fail-closed closeout audit for the immutable Round 5.11 campaign."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from .formal_acquisition_execution import TECHNICAL_FAILURE_CATEGORIES


SCHEMA_VERSION = 1
EXPECTED_ACCOUNTING = {
    "scheduled_units": 60,
    "resolved_units": 60,
    "dev_train_units": 45,
    "dev_tune_units": 15,
    "successful_tasks": 22,
    "scientific_task_failures": 38,
    "unresolved_technical_failures": 0,
    "train_decision_records": 608,
    "tune_decision_records": 179,
    "total_decision_records": 787,
    "holdout_units": 0,
    "holdout_records": 0,
    "final_evaluation_units": 0,
    "final_evaluation_records": 0,
}
EXPECTED_TECHNICAL_RETRIES = 20
RETRY_BINDING_FIELDS = (
    "collection_id",
    "development_input_release_id",
    "development_protocol_id",
    "role",
    "group_id",
    "task",
    "seed",
    "difficulty",
    "source_commit",
    "paper_memory_v5_release_id",
    "snapshot_root_sha256",
    "bootstrap_policy_id",
    "prompt_hash_bundle_id",
    "requested_model_name",
)
REQUIRED_EXECUTION_BUDGET_FIELDS = (
    "max_execution_attempts",
    "max_explore_steps",
    "episode_timeout_seconds",
)


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: str | Path) -> Mapping[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def load_jsonl(path: str | Path) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    for line_number, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, Mapping):
            raise ValueError(f"JSONL line {line_number} is not an object: {path}")
        records.append(payload)
    return records


def _correctness_table(
    records: Sequence[Mapping[str, Any]], field: str
) -> dict[str, Mapping[str, Any]]:
    values: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for record in records:
        key = str(record.get(field, "unknown"))
        values[key][0] += 1
        values[key][1] += int(bool(record.get("decision_correct")))
    return {
        key: {
            "count": count,
            "correct": correct,
            "incorrect": count - correct,
            "empirical_correctness": correct / count if count else None,
        }
        for key, (count, correct) in sorted(values.items())
    }


def _decision_accounting(
    records: Sequence[Mapping[str, Any]], role: str
) -> Mapping[str, Any]:
    selected = [record for record in records if record.get("role") == role]
    per_run = Counter(str(record.get("run_id", "")) for record in selected)
    records_per_run = Counter(per_run.values())
    correct = sum(bool(record.get("decision_correct")) for record in selected)
    hard_feasible = sum(bool(record.get("knowledge_hard_feasible")) for record in selected)
    knowledge_unknown = sum(bool(record.get("knowledge_unknown")) for record in selected)
    return {
        "record_count": len(selected),
        "decision_correct": {
            "true": correct,
            "false": len(selected) - correct,
        },
        "hard_feasible": {
            "true": hard_feasible,
            "false": len(selected) - hard_feasible,
        },
        "knowledge_unknown": {
            "true": knowledge_unknown,
            "false": len(selected) - knowledge_unknown,
        },
        "confidence_levels": _correctness_table(selected, "confidence_level"),
        "environment_states": _correctness_table(
            selected, "environment_raw_state"
        ),
        "task_count": len({str(record.get("task", "")) for record in selected}),
        "task_seed_count": len(
            {
                (str(record.get("task", "")), str(record.get("seed", "")))
                for record in selected
            }
        ),
        "run_count": len(per_run),
        "group_count": len(
            {str(record.get("group_id", "")) for record in selected}
        ),
        "records_per_run_distribution": {
            str(size): count for size, count in sorted(records_per_run.items())
        },
    }


def _attempt_category(summary: Mapping[str, Any]) -> str:
    for key in ("technical_failure_category", "failure_category", "category"):
        value = str(summary.get(key, "")).strip()
        if value:
            return value
    return "unrecorded"


def _audit_retry_lineage(
    campaign_root: str | Path,
    final_records: Sequence[Mapping[str, Any]],
    *,
    expected_technical_retries: int = EXPECTED_TECHNICAL_RETRIES,
) -> tuple[Mapping[str, Any], list[str]]:
    root = Path(campaign_root)
    runs_root = root / "runs"
    errors: list[str] = []
    accepted_markers = sorted(runs_root.glob("*/accepted.json"))
    final_record_ids = {
        str(record.get("record_id", "")) for record in final_records
    }
    final_run_ids = {str(record.get("run_id", "")) for record in final_records}
    categories: Counter[str] = Counter()
    total_attempts = 0
    retry_attempts = 0
    retried_units = 0
    scientific_failures_retried = 0
    lineage_mismatches = 0
    excluded_partial_rows = 0
    mixed_attempt_rows = 0
    preserved_failed_attempts = True
    retry_limit_violations = 0
    missing_budget_bindings = 0

    for marker_path in accepted_markers:
        marker = _load_json(marker_path)
        final_attempt = int(marker.get("attempt", -1))
        if final_attempt < 0:
            errors.append(f"{marker_path.parent.name}: invalid accepted attempt")
            continue
        attempts = sorted(
            marker_path.parent.glob("attempt-*"),
            key=lambda path: int(path.name.split("-")[-1]),
        )
        indices = [int(path.name.split("-")[-1]) for path in attempts]
        expected_indices = list(range(final_attempt + 1))
        if indices != expected_indices:
            errors.append(
                f"{marker.get('group_id', marker_path.parent.name)}: "
                "attempt lineage is not contiguous"
            )
        total_attempts += len(attempts)
        retry_attempts += max(0, len(attempts) - 1)
        retried_units += int(len(attempts) > 1)
        retry_limit_violations += int(final_attempt > 2)
        baseline_binding: Mapping[str, Any] | None = None

        for attempt_path in attempts:
            index = int(attempt_path.name.split("-")[-1])
            summary_path = attempt_path / "attempt_summary.json"
            binding_path = attempt_path / "run_binding.json"
            if not summary_path.is_file() or not binding_path.is_file():
                preserved_failed_attempts = False
                errors.append(
                    f"{marker.get('group_id', marker_path.parent.name)} "
                    f"attempt {index}: immutable summary/binding missing"
                )
                continue
            summary = _load_json(summary_path)
            binding = _load_json(binding_path)
            if baseline_binding is None:
                baseline_binding = binding
            else:
                differences = [
                    field
                    for field in RETRY_BINDING_FIELDS
                    if baseline_binding.get(field) != binding.get(field)
                ]
                if differences:
                    lineage_mismatches += 1
                    errors.append(
                        f"{marker.get('group_id', marker_path.parent.name)} "
                        f"attempt {index}: lineage mismatch in {differences}"
                    )
            if index < final_attempt:
                category = _attempt_category(summary)
                categories[category] += 1
                if category not in TECHNICAL_FAILURE_CATEGORIES:
                    errors.append(
                        f"{marker.get('group_id', marker_path.parent.name)} "
                        f"attempt {index}: unapproved technical category {category}"
                    )
                if bool(summary.get("pipeline_pass")) and not bool(
                    summary.get("task_completed")
                ):
                    scientific_failures_retried += 1
                partial_path = attempt_path / "development_decisions.jsonl"
                if partial_path.is_file():
                    partial = load_jsonl(partial_path)
                    excluded_partial_rows += len(partial)
                    mixed_attempt_rows += sum(
                        str(record.get("record_id", "")) in final_record_ids
                        for record in partial
                    )
            elif not (
                bool(summary.get("accepted"))
                and bool(summary.get("pipeline_pass"))
                and bool(summary.get("records_present"))
            ):
                errors.append(
                    f"{marker.get('group_id', marker_path.parent.name)}: "
                    "final attempt is not a valid accepted attempt"
                )
            for field in REQUIRED_EXECUTION_BUDGET_FIELDS:
                if field not in binding:
                    missing_budget_bindings += 1

        if str(marker.get("run_id", "")) not in final_run_ids:
            errors.append(
                f"{marker.get('group_id', marker_path.parent.name)}: "
                "accepted run has no final decision rows"
            )

    if retry_attempts != expected_technical_retries:
        errors.append(
            "technical retry accounting mismatch: "
            f"observed {retry_attempts}, expected {expected_technical_retries}"
        )
    if mixed_attempt_rows:
        errors.append("failed technical-attempt rows entered the final dataset")
    if scientific_failures_retried:
        errors.append("completed scientific failures were retried")
    if retry_limit_violations:
        errors.append("one or more task-seeds exceeded two technical retries")
    if missing_budget_bindings:
        errors.append("execution budgets are not bound in per-attempt lineage")

    return (
        {
            "total_attempts": total_attempts,
            "technical_retry_attempts": retry_attempts,
            "expected_technical_retry_attempts": expected_technical_retries,
            "unique_task_seeds_retried": retried_units,
            "retry_count_by_category": dict(sorted(categories.items())),
            "decision_rows_excluded_from_failed_technical_attempts": (
                excluded_partial_rows
            ),
            "mixed_attempt_decision_rows": mixed_attempt_rows,
            "scientific_failures_retried": scientific_failures_retried,
            "retry_lineage_mismatches": lineage_mismatches,
            "retry_limit_violations": retry_limit_violations,
            "failed_attempts_preserved": preserved_failed_attempts,
            "missing_execution_budget_bindings": missing_budget_bindings,
        },
        errors,
    )


def _artifact_entry(
    payload: Mapping[str, Any], id_keys: Sequence[str], eligible: bool
) -> Mapping[str, Any]:
    artifact_id = next(
        (str(payload[key]) for key in id_keys if str(payload.get(key, "")).strip()),
        "",
    )
    return {"artifact_id": artifact_id, "eligible": bool(artifact_id and eligible)}


def build_round511_closeout(
    *,
    baseline_sha: str,
    campaign_root: str | Path,
    campaign_summary_path: str | Path,
    train_decisions_path: str | Path,
    tune_decisions_path: str | Path,
    scene_lineage_audit_path: str | Path,
    development_protocol_path: str | Path,
    analysis_policy_path: str | Path,
    development_tooling_binding_path: str | Path,
    development_input_release_path: str | Path,
    collection_audit_path: str | Path,
    confidence_release_path: str | Path,
    environment_release_path: str | Path,
    fusion_release_path: str | Path,
    paper_memory_release_path: str | Path,
    active_taskset_release_path: str | Path,
    sealed_holdout_path: str | Path,
) -> Mapping[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    campaign_summary = _load_json(campaign_summary_path)
    train = load_jsonl(train_decisions_path)
    tune = load_jsonl(tune_decisions_path)
    records = train + tune
    accepted = [
        _load_json(path)
        for path in sorted(Path(campaign_root).glob("runs/*/accepted.json"))
    ]

    accounting = {
        "scheduled_units": int(campaign_summary.get("assignment_count", -1)),
        "resolved_units": len(accepted),
        "dev_train_units": sum(item.get("role") == "dev_train" for item in accepted),
        "dev_tune_units": sum(item.get("role") == "dev_tune" for item in accepted),
        "successful_tasks": sum(bool(item.get("task_completed")) for item in accepted),
        "scientific_task_failures": sum(
            not bool(item.get("task_completed")) for item in accepted
        ),
        "unresolved_technical_failures": max(
            0, int(campaign_summary.get("assignment_count", 0)) - len(accepted)
        ),
        "train_decision_records": len(train),
        "tune_decision_records": len(tune),
        "total_decision_records": len(records),
        "holdout_units": 0,
        "holdout_records": sum(item.get("role") == "dev_holdout" for item in records),
        "final_evaluation_units": 0,
        "final_evaluation_records": sum(
            not bool(item.get("excluded_from_final_evaluation", False))
            for item in records
        ),
    }
    for key, expected in EXPECTED_ACCOUNTING.items():
        if accounting[key] != expected:
            errors.append(
                f"campaign accounting {key}: observed {accounting[key]}, expected {expected}"
            )
    if int(campaign_summary.get("completed_assignment_count", -1)) != 60:
        errors.append("campaign summary does not record 60 completed assignments")
    if int(campaign_summary.get("technical_failure_attempt_count", -1)) != 20:
        errors.append("campaign summary technical retry count is not 20")
    if bool(campaign_summary.get("holdout_accessed")):
        errors.append("campaign summary records holdout access")
    if bool(campaign_summary.get("final_evaluation_started")):
        errors.append("campaign summary records final evaluation access")

    retry_audit, retry_errors = _audit_retry_lineage(campaign_root, records)
    errors.extend(retry_errors)

    protocol = _load_json(development_protocol_path)
    roots_before = {str(item.get("snapshot_root_sha256_before", "")) for item in records}
    roots_after = {str(item.get("snapshot_root_sha256_after", "")) for item in records}
    memory_ids = {str(item.get("paper_memory_v5_release_id", "")) for item in records}
    protected = {
        "paper_memory_v5_release_count": len(memory_ids),
        "snapshot_root_count": len(roots_before | roots_after),
        "snapshot_before_equals_after": all(
            item.get("snapshot_root_sha256_before")
            == item.get("snapshot_root_sha256_after")
            for item in records
        ),
        "formal_memory_writes": sum(
            int(item.get("formal_memory_write_count", 0)) for item in records
        ),
        "acquisition_store_writes": sum(
            int(item.get("acquisition_write_count", 0)) for item in records
        ),
        "evaluation_chain_calls": sum(
            int(item.get("evaluation_chain_calls", 0)) for item in records
        ),
        "mine_sand_records": sum(item.get("task") == "mine sand" for item in records),
        "final_heldout_task_contamination": int(
            protocol.get("final_heldout_contamination_count", -1)
        ),
        "final_task_seed_contamination": int(
            protocol.get("final_seed_contamination_count", -1)
        ),
        "holdout_records_or_accesses": sum(
            item.get("role") == "dev_holdout" or bool(item.get("holdout_accessed"))
            for item in records
        ),
        "final_evaluation_records_or_accesses": sum(
            not bool(item.get("excluded_from_final_evaluation", False))
            for item in records
        ),
        "sealed_holdout_sha256": sha256_file(sealed_holdout_path),
        "sealed_holdout_hash_matches_protocol": (
            sha256_file(sealed_holdout_path)
            == str(protocol.get("holdout_sealed_manifest_hash", ""))
        ),
    }
    protected_expected = {
        "paper_memory_v5_release_count": 1,
        "snapshot_root_count": 1,
        "snapshot_before_equals_after": True,
        "formal_memory_writes": 0,
        "acquisition_store_writes": 0,
        "evaluation_chain_calls": 0,
        "mine_sand_records": 0,
        "final_heldout_task_contamination": 0,
        "final_task_seed_contamination": 0,
        "holdout_records_or_accesses": 0,
        "final_evaluation_records_or_accesses": 0,
        "sealed_holdout_hash_matches_protocol": True,
    }
    for key, expected in protected_expected.items():
        if protected[key] != expected:
            errors.append(f"protected-data invariant failed: {key}")

    scene = _load_json(scene_lineage_audit_path)
    analysis = _load_json(analysis_policy_path)
    tooling = _load_json(development_tooling_binding_path)
    input_release = _load_json(development_input_release_path)
    collection = _load_json(collection_audit_path)
    confidence = _load_json(confidence_release_path)
    environment = _load_json(environment_release_path)
    fusion = _load_json(fusion_release_path)
    paper_memory = _load_json(paper_memory_release_path)
    taskset = _load_json(active_taskset_release_path)
    artifacts = {
        "SceneLineageAudit": _artifact_entry(scene, ("audit_id",), bool(scene.get("eligible"))),
        "DevelopmentSplitProtocol": _artifact_entry(
            protocol, ("protocol_id",), bool(protocol.get("eligible"))
        ),
        "Round511AnalysisPolicy": _artifact_entry(
            analysis,
            ("policy_id",),
            bool(analysis.get("policy_frozen_before_collection"))
            and not bool(analysis.get("holdout_use_permitted"))
            and not bool(analysis.get("final_evaluation_use_permitted")),
        ),
        "DevelopmentToolingBinding": _artifact_entry(
            tooling,
            ("binding_id", "adjustment_id"),
            bool(tooling.get("approved_by") or tooling.get("author_approval_record_id"))
            and not bool(tooling.get("final_evaluation_started")),
        ),
        "DevelopmentInputRelease": _artifact_entry(
            input_release, ("release_id",), bool(input_release.get("eligible"))
        ),
        "DevelopmentCollectionAudit": _artifact_entry(
            collection, ("audit_id",), bool(collection.get("eligible"))
        ),
        "ConfidenceCalibrationRelease": _artifact_entry(
            confidence,
            ("release_id",),
            bool(confidence.get("eligible"))
            and not bool(confidence.get("holdout_used"))
            and not bool(confidence.get("final_evaluation_used")),
        ),
        "EnvironmentEvidenceRelease": _artifact_entry(
            environment,
            ("release_id",),
            bool(environment.get("eligible"))
            and not bool(environment.get("holdout_used"))
            and not bool(environment.get("final_evaluation_used")),
        ),
        "FusionFeatureDatasetRelease": _artifact_entry(
            fusion,
            ("release_id",),
            bool(fusion.get("eligible"))
            and not bool(fusion.get("fusion_fitted"))
            and not bool(fusion.get("holdout_used"))
            and not bool(fusion.get("final_evaluation_used")),
        ),
    }
    for name, item in artifacts.items():
        if not item["eligible"]:
            errors.append(f"required Round 5.11 artifact is ineligible: {name}")

    cross_bindings = {
        "protocol": str(input_release.get("development_protocol_id", ""))
        == artifacts["DevelopmentSplitProtocol"]["artifact_id"],
        "analysis_policy": str(input_release.get("analysis_policy_id", ""))
        == artifacts["Round511AnalysisPolicy"]["artifact_id"],
        "tooling": str(input_release.get("development_tooling_binding_id", ""))
        == artifacts["DevelopmentToolingBinding"]["artifact_id"],
        "scene_lineage": str(input_release.get("scene_lineage_audit_id", ""))
        == artifacts["SceneLineageAudit"]["artifact_id"],
        "collection_audit": str(fusion.get("collection_audit_id", ""))
        == artifacts["DevelopmentCollectionAudit"]["artifact_id"],
        "confidence": str(fusion.get("confidence_calibration_release_id", ""))
        == artifacts["ConfidenceCalibrationRelease"]["artifact_id"],
        "environment": str(fusion.get("environment_evidence_release_id", ""))
        == artifacts["EnvironmentEvidenceRelease"]["artifact_id"],
        "paper_memory": str(input_release.get("paper_memory_v5_release_id", ""))
        == str(paper_memory.get("release_id", ""))
        == str(fusion.get("paper_memory_v5_release_id", "")),
        "active_taskset": str(input_release.get("active_taskset_release_id", ""))
        == str(taskset.get("release_id", ""))
        == str(fusion.get("active_taskset_release_id", "")),
    }
    for name, valid in cross_bindings.items():
        if not valid:
            errors.append(f"Round 5.11 artifact cross-binding failed: {name}")

    record_ids = [str(item.get("record_id", "")) for item in records]
    record_hashes = [str(item.get("record_hash", "")) for item in records]
    if len(record_ids) != len(set(record_ids)):
        errors.append("duplicate decision record IDs are present")
    if len(record_hashes) != len(set(record_hashes)):
        errors.append("duplicate decision record hashes are present")

    redstone = [item for item in accepted if item.get("task") == "craft redstone torch"]
    if not redstone or any(bool(item.get("task_completed")) for item in redstone):
        errors.append("redstone-torch scientific failures are not preserved")

    warnings.append(
        "Round 5.11 used approved runtime transitions; this closeout does not "
        "claim a single immutable Controller revision."
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "round511_base_sha": baseline_sha,
        "campaign_accounting": accounting,
        "retry_audit": retry_audit,
        "protected_data_checks": protected,
        "decision_accounting": {
            role: _decision_accounting(records, role)
            for role in ("dev_train", "dev_tune")
        },
        "artifacts": artifacts,
        "artifact_cross_bindings": cross_bindings,
        "paper_memory_v5_release_id": str(paper_memory.get("release_id", "")),
        "active_taskset_release_id": str(taskset.get("release_id", "")),
        "duplicate_decision_record_ids": len(record_ids) - len(set(record_ids)),
        "duplicate_decision_record_hashes": len(record_hashes) - len(set(record_hashes)),
        "eligible": not errors,
        "errors": list(dict.fromkeys(errors)),
        "warnings": warnings,
        "holdout_opened": False,
        "final_evaluation_accessed": False,
        "round6_started": False,
    }
    payload["report_id"] = _sha(payload)
    return payload


def write_closeout_report(path: str | Path, report: Mapping[str, Any]) -> None:
    output = Path(path)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite closeout report: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
