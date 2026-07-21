"""External-evidence audit for the Round 5.12.4 standard closeout."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .development_records import load_development_record
from .round5124_contracts import (
    L2ProvenanceAudit,
    Round5124BootstrapPolicy,
    STANDARDIZATION_DECISION,
    StandardDevelopmentCloseout,
    StandardDevelopmentDatasetAcceptance,
    StandardIntegrityCounts,
    StandardizationDecision,
    StandardReplacementLineage,
)


HISTORICAL_L2_COMMIT = "208ebf9e2c3d07ff15bf963278e6df54710aee77"
HISTORICAL_ACTIVATION_POLICY_ID = (
    "982040766d9f09b6466e8b6f44de85a1108001e26a7f102431df76913767fb07"
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
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _load_jsonl(path: str | Path) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for line_number, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise ValueError(f"Expected JSON object at {path}:{line_number}")
        rows.append(value)
    return rows


def _dataset_id(records: Sequence[Mapping[str, Any]]) -> str:
    return _sha(
        [
            {
                "record_id": str(item["record_id"]),
                "record_hash": str(item["record_hash"]),
            }
            for item in sorted(records, key=lambda value: str(value["record_id"]))
        ]
    )


@dataclass(frozen=True)
class StandardCloseoutInputs:
    source_commit: str
    author_prompt_path: Path
    author_effective_date: str
    campaign_roots: tuple[Path, ...]
    assignments_path: Path
    continuation_manifest_path: Path
    continuation_approval_path: Path
    effective_status_path: Path
    effective_train_path: Path
    effective_tune_path: Path
    development_input_release_path: Path
    analysis_policy_path: Path
    paper_memory_release_path: Path
    active_taskset_release_path: Path
    formal_log_bootstrap_policy_path: Path
    historical_runtime_manifest_path: Path


@dataclass(frozen=True)
class _AttemptEvidence:
    marker_path: Path
    campaign_root: Path
    marker: Mapping[str, Any]
    attempt_path: Path
    records_path: Path
    receipt_path: Path
    records: tuple[Mapping[str, Any], ...]


def _attempt_evidence(marker_path: Path) -> _AttemptEvidence:
    marker = _load_json(marker_path)
    campaign_root = marker_path.parents[2]
    attempt_index = int(marker.get("attempt", -1))
    if attempt_index < 0:
        raise ValueError(f"Invalid attempt index: {marker_path}")
    attempt_path = marker_path.parent / f"attempt-{attempt_index}"
    records_path = campaign_root / str(marker.get("records", ""))
    receipt_path = campaign_root / str(marker.get("receipt", ""))
    required = (
        attempt_path / "run_binding.json",
        attempt_path / "execution_budget_snapshot.json",
        records_path,
        receipt_path,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError(f"Attempt evidence is incomplete: {missing}")
    records = tuple(_load_jsonl(records_path))
    if not records:
        raise ValueError(f"Accepted attempt has no decisions: {marker_path}")
    return _AttemptEvidence(
        marker_path=marker_path,
        campaign_root=campaign_root,
        marker=marker,
        attempt_path=attempt_path,
        records_path=records_path,
        receipt_path=receipt_path,
        records=records,
    )


def _attempt_sha(item: _AttemptEvidence) -> str:
    return _sha(
        {
            "accepted_marker_sha256": sha256_file(item.marker_path),
            "run_binding_sha256": sha256_file(
                item.attempt_path / "run_binding.json"
            ),
            "budget_snapshot_sha256": sha256_file(
                item.attempt_path / "execution_budget_snapshot.json"
            ),
            "receipt_sha256": sha256_file(item.receipt_path),
            "decision_jsonl_sha256": sha256_file(item.records_path),
        }
    )


def _replacement_lineage(
    *,
    outcomes: Sequence[Mapping[str, Any]],
    evidence: Sequence[_AttemptEvidence],
    effective_record_ids: set[str],
    continuation_approval: Mapping[str, Any],
) -> StandardReplacementLineage:
    superseded = [item for item in outcomes if bool(item.get("superseded"))]
    if len(superseded) != 1:
        raise ValueError("Expected one resumed replacement")
    outcome = superseded[0]
    group_id = str(outcome.get("group_id", ""))
    selected_run_id = str(outcome.get("selected_run_id", ""))
    candidates = [
        item for item in evidence if item.marker.get("group_id") == group_id
    ]
    replacements = [
        item for item in candidates if item.marker.get("run_id") == selected_run_id
    ]
    old = [
        item
        for item in candidates
        if item.marker.get("run_id") != selected_run_id
        and item.marker.get("status") == "completed_scientific_failure"
    ]
    if len(replacements) != 1 or len(old) != 1:
        raise ValueError("Replacement lineage is incomplete")
    replacement = replacements[0]
    old_ids = {
        str(record["record_id"]) for item in old for record in item.records
    }
    marker = replacement.marker
    return StandardReplacementLineage(
        assignment_id=group_id,
        task=str(marker["task"]),
        seed=str(marker["seed"]),
        role=str(marker["role"]),
        old_failed_attempt_ids=tuple(
            f"{item.marker['run_id']}:attempt-{item.marker['attempt']}"
            for item in old
        ),
        old_failed_attempt_sha256=tuple(_attempt_sha(item) for item in old),
        replacement_attempt_id=(
            f"{marker['run_id']}:attempt-{marker['attempt']}"
        ),
        replacement_attempt_sha256=_attempt_sha(replacement),
        authorization_id=str(continuation_approval.get("approval_id", "")),
        old_failed_attempt_rows=sum(len(item.records) for item in old),
        old_failed_attempt_rows_included=len(
            old_ids.intersection(effective_record_ids)
        ),
        resumed_accepted_rows=len(replacement.records),
        accepted_final_attempts=sum(
            item.get("group_id") == group_id for item in outcomes
        ),
        final_status=str(outcome.get("status", "")),
    ).with_id()


def _all_attempt_evidence(roots: Sequence[Path]) -> tuple[_AttemptEvidence, ...]:
    by_marker: dict[Path, _AttemptEvidence] = {}
    for root in roots:
        for marker_path in sorted(Path(root).glob("runs/*/accepted.json")):
            resolved = marker_path.resolve()
            by_marker[resolved] = _attempt_evidence(marker_path)
    return tuple(by_marker[path] for path in sorted(by_marker))


def build_standard_acceptance(
    inputs: StandardCloseoutInputs,
) -> tuple[
    StandardizationDecision,
    StandardDevelopmentDatasetAcceptance,
    StandardDevelopmentCloseout,
]:
    assignments_payload = _load_json(inputs.assignments_path)
    assignments = assignments_payload.get("assignments")
    if not isinstance(assignments, list) or len(assignments) != 60:
        raise ValueError("Assignment manifest must contain 60 units")
    assignments_by_group = {str(item["group_id"]): item for item in assignments}
    if len(assignments_by_group) != 60:
        raise ValueError("Assignment groups are not unique")

    status = _load_json(inputs.effective_status_path)
    outcomes = status.get("outcomes")
    if not isinstance(outcomes, list) or len(outcomes) != 60:
        raise ValueError("Effective status must contain 60 outcomes")
    selected_run_ids = {str(item.get("selected_run_id", "")) for item in outcomes}
    if len(selected_run_ids) != 60 or "" in selected_run_ids:
        raise ValueError("Effective status selected run IDs are invalid")

    train = _load_jsonl(inputs.effective_train_path)
    tune = _load_jsonl(inputs.effective_tune_path)
    effective = train + tune
    for row in effective:
        load_development_record(row)
    effective_by_id = {str(item["record_id"]): item for item in effective}
    duplicate_ids = len(effective) - len(effective_by_id)

    evidence = _all_attempt_evidence(inputs.campaign_roots)
    selected = [
        item for item in evidence if item.marker.get("run_id") in selected_run_ids
    ]
    if len(selected) != 60:
        raise ValueError(f"Selected evidence count changed: {len(selected)}")
    selected_records = [record for item in selected for record in item.records]
    selected_by_id = {str(item["record_id"]): item for item in selected_records}
    if set(selected_by_id) != set(effective_by_id):
        raise ValueError("Effective dataset differs from selected attempts")
    if any(
        selected_by_id[key].get("record_hash")
        != effective_by_id[key].get("record_hash")
        for key in effective_by_id
    ):
        raise ValueError("Effective decision record was altered")

    outcome_groups = {str(item.get("group_id", "")) for item in outcomes}
    if outcome_groups != set(assignments_by_group):
        raise ValueError("Effective outcomes differ from frozen assignments")
    for item in selected:
        group_id = str(item.marker.get("group_id", ""))
        assignment = assignments_by_group[group_id]
        for field in ("role", "task", "seed"):
            if str(item.marker.get(field, "")) != str(assignment.get(field, "")):
                raise ValueError(f"{group_id}: accepted marker {field} drift")

    selected_paths = {item.records_path.resolve() for item in selected}
    nonselected_ids: set[str] = set()
    for root in inputs.campaign_roots:
        for path in Path(root).glob("runs/*/**/development_decisions.jsonl"):
            if path.resolve() in selected_paths:
                continue
            nonselected_ids.update(
                str(item.get("record_id", "")) for item in _load_jsonl(path)
            )

    continuation = _load_json(inputs.continuation_manifest_path)
    continuation_approval = _load_json(inputs.continuation_approval_path)
    development_input = _load_json(inputs.development_input_release_path)
    analysis_policy = _load_json(inputs.analysis_policy_path)
    paper_memory = _load_json(inputs.paper_memory_release_path)
    taskset = _load_json(inputs.active_taskset_release_path)
    bootstrap = _load_json(inputs.formal_log_bootstrap_policy_path)
    historical = _load_json(inputs.historical_runtime_manifest_path)
    if str(development_input.get("analysis_policy_id")) != str(
        analysis_policy.get("policy_id")
    ):
        raise ValueError("Development input and analysis policy differ")
    if str(development_input.get("paper_memory_v5_release_id")) != str(
        paper_memory.get("release_id")
    ):
        raise ValueError("Development input and Paper Memory V5 differ")
    if str(development_input.get("active_taskset_release_id")) != str(
        taskset.get("release_id")
    ):
        raise ValueError("Development input and active taskset differ")
    if str(development_input.get("formal_bootstrap_policy_id")) != str(
        bootstrap.get("policy_id")
    ):
        raise ValueError("Development input and Log Bootstrap policy differ")

    roots = {
        str(item.get("snapshot_root_sha256_before", "")) for item in effective
    } | {str(item.get("snapshot_root_sha256_after", "")) for item in effective}
    roots.discard("")
    success_count = sum(item.get("status") == "completed_success" for item in outcomes)
    failure_count = sum(
        item.get("status") == "completed_scientific_failure" for item in outcomes
    )
    train_groups = {str(item["group_id"]) for item in train}
    tune_groups = {str(item["group_id"]) for item in tune}
    integrity = StandardIntegrityCounts(
        resolved_units=len(outcomes),
        train_units=len(train_groups),
        tune_units=len(tune_groups),
        task_successes=success_count,
        scientific_failures=failure_count,
        pending_units=len(outcomes) - success_count - failure_count,
        train_decisions=len(train),
        tune_decisions=len(tune),
        failed_attempt_decision_contamination=len(
            nonselected_ids.intersection(effective_by_id)
        ),
        duplicate_accepted_decision_ids=duplicate_ids,
        formal_memory_writes=sum(
            int(item.get("formal_memory_write_count", 0)) for item in effective
        ),
        acquisition_store_writes=sum(
            int(item.get("acquisition_write_count", 0)) for item in effective
        ),
        evaluation_chain_calls=sum(
            int(item.get("evaluation_chain_calls", 0)) for item in effective
        ),
        holdout_accesses_or_records=sum(
            bool(item.get("holdout_accessed"))
            or item.get("role") == "dev_holdout"
            for item in effective
        ),
        final_accesses_or_records=sum(
            not bool(item.get("excluded_from_final_evaluation", False))
            for item in effective
        ),
        mine_sand_records=sum(item.get("task") == "mine sand" for item in effective),
        paper_memory_v5_snapshot_roots=len(roots),
    )
    lineage = _replacement_lineage(
        outcomes=outcomes,
        evidence=evidence,
        effective_record_ids=set(effective_by_id),
        continuation_approval=continuation_approval,
    )
    decision = StandardizationDecision(
        approved_by="ZYF",
        decision_text=STANDARDIZATION_DECISION,
        source_prompt_sha256=sha256_file(inputs.author_prompt_path),
        effective_date=inputs.author_effective_date,
        all_60_units_accepted=True,
        all_681_records_accepted=True,
        no_development_rerun=True,
        standard_scientific_condition=True,
        runtime_segment_modeling=False,
        runtime_segment_is_predictive_feature=False,
        runtime_segment_is_eligibility_gate=False,
        one_frozen_runtime_required_for_holdout=True,
        model_identity_differences_ignored=True,
    ).with_id()
    acceptance = StandardDevelopmentDatasetAcceptance(
        acceptance_name="round5124-standard-development-dataset-acceptance",
        source_commit=inputs.source_commit,
        standardization_decision_id=decision.decision_id,
        assignment_manifest_id=str(continuation.get("assignment_manifest_id", "")),
        assignment_manifest_sha256=sha256_file(inputs.assignments_path),
        effective_status_sha256=sha256_file(inputs.effective_status_path),
        train_dataset_id=_dataset_id(train),
        train_jsonl_sha256=sha256_file(inputs.effective_train_path),
        tune_dataset_id=_dataset_id(tune),
        tune_jsonl_sha256=sha256_file(inputs.effective_tune_path),
        paper_memory_v5_release_id=str(paper_memory.get("release_id", "")),
        paper_memory_v5_snapshot_root_sha256=str(
            paper_memory.get("snapshot_root_sha256", "")
        ),
        active_taskset_release_id=str(taskset.get("release_id", "")),
        analysis_policy_id=str(analysis_policy.get("policy_id", "")),
        formal_log_bootstrap_policy_id=str(bootstrap.get("policy_id", "")),
        historical_runtime_segment_manifest_id=str(historical.get("manifest_id", "")),
        historical_runtime_segment_manifest_sha256=sha256_file(
            inputs.historical_runtime_manifest_path
        ),
        replacement_lineage=lineage,
        integrity=integrity,
        standard_scientific_condition=True,
        mixed_runtime_modeling=False,
        runtime_segment_is_predictive_feature=False,
        runtime_segment_is_eligibility_gate=False,
        holdout_opened=False,
        fusion_fitted=False,
        final_evaluation_opened=False,
        eligible=True,
    ).with_id()
    closeout = StandardDevelopmentCloseout(
        closeout_name="round5124-standard-development-closeout",
        source_commit=inputs.source_commit,
        acceptance_id=acceptance.acceptance_id,
        development_success_rate=success_count / len(outcomes),
        train_label_counts=dict(
            Counter("true" if item["decision_correct"] else "false" for item in train)
        ),
        tune_label_counts=dict(
            Counter("true" if item["decision_correct"] else "false" for item in tune)
        ),
        train_group_count=len(train_groups),
        tune_group_count=len(tune_groups),
        train_task_count=len({str(item["task"]) for item in train}),
        tune_task_count=len({str(item["task"]) for item in tune}),
        holdout_opened=False,
        fusion_fitted=False,
        final_evaluation_opened=False,
        eligible=True,
    ).with_id()
    return decision, acceptance, closeout


def _git_file(repo_root: Path, commit: str, relative_path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout


def build_l2_provenance_audit(repo_root: str | Path) -> L2ProvenanceAudit:
    root = Path(repo_root)
    trainer_path = "MP5_agent/dc3pa/reliability/fusion_training.py"
    cli_path = "MP5_agent/scripts_dc3pa/fit_monotonic_fusion.py"
    trainer = _git_file(root, HISTORICAL_L2_COMMIT, trainer_path)
    cli = _git_file(root, HISTORICAL_L2_COMMIT, cli_path)
    required_trainer = (
        "l2: float = 1e-3",
        "grad_w = (x_train.T @ residual) / len(y_train) + config.l2 * coefficients",
        "grad_b = float(residual.mean())",
    )
    if any(value not in trainer for value in required_trainer):
        raise ValueError("Historical trainer no longer proves fixed L2 semantics")
    if 'parser.add_argument("--l2", type=float, default=1e-3)' not in cli:
        raise ValueError("Historical CLI no longer proves fixed L2 default")
    return L2ProvenanceAudit(
        case=2,
        source_commit=HISTORICAL_L2_COMMIT,
        source_paths=(trainer_path, cli_path),
        source_json_pointers=(
            "/TrainerConfig/l2",
            "/argparse/--l2/default",
        ),
        candidate_values=(1e-3,),
        loss_definition="mean_binary_negative_log_likelihood",
        regularization_definition="0.5*l2*sum(beta_j^2)",
        intercept_regularized=False,
        feature_scaling="none_features_used_on_native_0_1_scale",
        sample_weighting="equal_per_decision_record",
        development_outcomes_existed_when_frozen=False,
        numeric_value_invented=False,
        eligible_for_fit=True,
    ).with_id()


def build_bootstrap_policy(
    activation_policy_path: str | Path,
) -> Round5124BootstrapPolicy:
    payload = _load_json(activation_policy_path)
    if str(payload.get("policy_id")) != HISTORICAL_ACTIVATION_POLICY_ID:
        raise ValueError("Unexpected historical activation policy")
    if payload.get("bootstrap_grouping") != "task":
        raise ValueError("Historical activation bootstrap is not task-grouped")
    return Round5124BootstrapPolicy(
        historical_activation_policy_id=HISTORICAL_ACTIVATION_POLICY_ID,
        historical_activation_policy_sha256=sha256_file(activation_policy_path),
        primary_bootstrap_unit="task",
        secondary_sensitivity_bootstrap_unit="task_seed_run",
        decision_row_iid_bootstrap_forbidden=True,
        primary_controls_activation=True,
        secondary_can_override_activation=False,
        bootstrap_replicates=int(payload["bootstrap_replicates"]),
        bootstrap_seed=int(payload["bootstrap_seed"]),
        confidence_level=float(payload["confidence_level"]),
        reliability_bins=int(payload["ece_bins"]),
        noninferiority_margins=dict(payload["noninferiority_margins"]),
        minimum_effects=dict(payload["minimum_effects"]),
        minimum_primary_improvements=int(payload["minimum_primary_improvements"]),
        require_improvement_ci_upper_at_most_zero=bool(
            payload["require_improvement_ci_upper_at_most_zero"]
        ),
    ).with_id()


def write_json_immutable(path: str | Path, value: Mapping[str, Any]) -> None:
    output = Path(path)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite immutable artifact: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
