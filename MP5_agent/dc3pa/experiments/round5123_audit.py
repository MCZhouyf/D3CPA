"""Build the external Round 5.12.3 runtime-segment audit artifacts."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .round5123_contracts import (
    AcceptedUnitBinding,
    MixedRuntimeDevelopmentAmendment,
    ResumedReplacementLineage,
    RuntimeSegment,
    RuntimeSegmentManifest,
)


SourceIdentityResolver = Callable[[str], Mapping[str, Any]]


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
        raise ValueError(f"expected JSON object: {path}")
    return value


def _load_jsonl(path: str | Path) -> list[Mapping[str, Any]]:
    records: list[Mapping[str, Any]] = []
    for line_number, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise ValueError(f"JSONL line {line_number} is not an object: {path}")
        records.append(value)
    return records


def _git_file(repo_root: Path, commit: str, relative_path: str) -> bytes:
    try:
        return subprocess.check_output(
            ["git", "show", f"{commit}:{relative_path}"],
            cwd=repo_root,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(
            f"cannot resolve {relative_path} at {commit}: {message}"
        ) from exc


def git_source_identity_resolver(repo_root: str | Path) -> SourceIdentityResolver:
    root = Path(repo_root).resolve()
    cache: dict[str, Mapping[str, Any]] = {}

    def resolve(commit: str) -> Mapping[str, Any]:
        if commit in cache:
            return cache[commit]
        components = {
            "MP5_agent/agent/controller.py": hashlib.sha256(
                _git_file(root, commit, "MP5_agent/agent/controller.py")
            ).hexdigest(),
            "MP5_agent/agent/structured_actions.py": hashlib.sha256(
                _git_file(root, commit, "MP5_agent/agent/structured_actions.py")
            ).hexdigest(),
        }
        result = {
            "controller_component_sha256": components,
            "controller_identity_sha256": _sha(components),
            "evaluator_identity_sha256": hashlib.sha256(
                _git_file(root, commit, "MP5_agent/agent/run_agent.py")
            ).hexdigest(),
        }
        cache[commit] = result
        return result

    return resolve


@dataclass(frozen=True)
class Round5123AuditInputs:
    round5122_result_sha: str
    campaign_roots: tuple[Path, ...]
    assignments_path: Path
    effective_status_path: Path
    effective_train_path: Path
    effective_tune_path: Path
    continuation_manifest_path: Path
    continuation_approval_path: Path
    development_input_release_path: Path
    paper_memory_release_path: Path
    active_taskset_release_path: Path
    formal_log_bootstrap_policy_path: Path


@dataclass(frozen=True)
class _AcceptedEvidence:
    marker_path: Path
    campaign_root: Path
    marker: Mapping[str, Any]
    attempt_path: Path
    run_binding: Mapping[str, Any]
    budget_snapshot: Mapping[str, Any]
    receipt: Mapping[str, Any]
    records: tuple[Mapping[str, Any], ...]
    records_path: Path


def _accepted_evidence(marker_path: Path) -> _AcceptedEvidence:
    marker = _load_json(marker_path)
    campaign_root = marker_path.parents[2]
    attempt_index = int(marker.get("attempt", -1))
    if attempt_index < 0:
        raise ValueError(f"invalid accepted attempt: {marker_path}")
    attempt_path = marker_path.parent / f"attempt-{attempt_index}"
    records_path = campaign_root / str(marker.get("records", ""))
    receipt_path = campaign_root / str(marker.get("receipt", ""))
    required = (
        attempt_path / "run_binding.json",
        attempt_path / "execution_budget_snapshot.json",
        receipt_path,
        records_path,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError(f"accepted evidence is incomplete: {missing}")
    records = tuple(_load_jsonl(records_path))
    if not records:
        raise ValueError(f"accepted run has no decision rows: {marker_path}")
    return _AcceptedEvidence(
        marker_path=marker_path,
        campaign_root=campaign_root,
        marker=marker,
        attempt_path=attempt_path,
        run_binding=_load_json(attempt_path / "run_binding.json"),
        budget_snapshot=_load_json(attempt_path / "execution_budget_snapshot.json"),
        receipt=_load_json(receipt_path),
        records=records,
        records_path=records_path,
    )


def _attempt_evidence_sha(item: _AcceptedEvidence) -> str:
    return _sha(
        {
            "accepted_marker_sha256": sha256_file(item.marker_path),
            "run_binding_sha256": sha256_file(item.attempt_path / "run_binding.json"),
            "budget_snapshot_sha256": sha256_file(
                item.attempt_path / "execution_budget_snapshot.json"
            ),
            "receipt_sha256": sha256_file(
                item.campaign_root / str(item.marker["receipt"])
            ),
            "decision_jsonl_sha256": sha256_file(item.records_path),
        }
    )


def _validate_static_releases(
    *,
    development_input: Mapping[str, Any],
    paper_memory: Mapping[str, Any],
    taskset: Mapping[str, Any],
    bootstrap: Mapping[str, Any],
) -> None:
    checks = {
        "Paper Memory V5 release": (
            development_input.get("paper_memory_v5_release_id"),
            paper_memory.get("release_id"),
        ),
        "active taskset release": (
            development_input.get("active_taskset_release_id"),
            taskset.get("release_id"),
        ),
        "formal Log Bootstrap policy": (
            development_input.get("formal_bootstrap_policy_id"),
            bootstrap.get("policy_id"),
        ),
    }
    for label, values in checks.items():
        if not values[0] or values[0] != values[1]:
            raise ValueError(f"{label} cross-binding failed: {values}")
    if not bool(paper_memory.get("eligible")):
        raise ValueError("Paper Memory V5 release is ineligible")
    if not bool(taskset.get("eligible")):
        raise ValueError("active taskset release is ineligible")


def _validate_unit_evidence(
    item: _AcceptedEvidence,
    *,
    development_input: Mapping[str, Any],
    paper_memory_root: str,
) -> None:
    binding = item.run_binding
    snapshot = item.budget_snapshot
    marker = item.marker
    records = item.records
    source_commits = {str(record.get("source_commit", "")) for record in records}
    if len(source_commits) != 1:
        raise ValueError(f"{marker.get('group_id')}: decision rows cross source commits")
    source_commit = next(iter(source_commits))
    if not (
        source_commit
        == str(binding.get("source_commit", ""))
        == str(snapshot.get("source_commit", ""))
    ):
        raise ValueError(f"{marker.get('group_id')}: runtime source binding mismatch")
    budget_id = str(marker.get("execution_budget_snapshot_id", ""))
    if not (
        budget_id
        == str(binding.get("execution_budget_snapshot_id", ""))
        == str(snapshot.get("snapshot_id", ""))
    ):
        raise ValueError(f"{marker.get('group_id')}: budget snapshot binding mismatch")
    static_fields = {
        "group_id": marker.get("group_id"),
        "run_id": marker.get("run_id"),
        "role": marker.get("role"),
        "task": marker.get("task"),
        "seed": marker.get("seed"),
        "development_input_release_id": development_input.get("release_id"),
        "development_protocol_id": development_input.get("development_protocol_id"),
        "prompt_hash_bundle_id": development_input.get("prompt_hash_bundle_id"),
        "paper_memory_v5_release_id": development_input.get(
            "paper_memory_v5_release_id"
        ),
        "bootstrap_policy_id": development_input.get("formal_bootstrap_policy_id"),
    }
    for field, expected in static_fields.items():
        if any(record.get(field) != expected for record in records):
            raise ValueError(
                f"{marker.get('group_id')}: decision row {field} binding mismatch"
            )
        if field in binding and binding.get(field) != expected:
            raise ValueError(
                f"{marker.get('group_id')}: run binding {field} mismatch"
            )
    if any(
        record.get("snapshot_root_sha256_before") != paper_memory_root
        or record.get("snapshot_root_sha256_after") != paper_memory_root
        for record in records
    ):
        raise ValueError(f"{marker.get('group_id')}: Paper Memory V5 root changed")


def _build_replacement_lineage(
    *,
    outcomes: Sequence[Mapping[str, Any]],
    evidence_by_group: Mapping[str, Sequence[_AcceptedEvidence]],
    effective_record_ids: set[str],
    continuation_approval: Mapping[str, Any],
) -> ResumedReplacementLineage:
    superseded = [item for item in outcomes if bool(item.get("superseded"))]
    if len(superseded) != 1:
        raise ValueError("expected exactly one resumed replacement lineage")
    outcome = superseded[0]
    group_id = str(outcome.get("group_id", ""))
    selected_run_id = str(outcome.get("selected_run_id", ""))
    candidates = tuple(evidence_by_group.get(group_id, ()))
    replacement = [
        item for item in candidates if item.marker.get("run_id") == selected_run_id
    ]
    old = [
        item
        for item in candidates
        if item.marker.get("run_id") != selected_run_id
        and item.marker.get("status") == "completed_scientific_failure"
    ]
    if len(replacement) != 1 or not old:
        raise ValueError("resumed replacement evidence is incomplete")
    replacement_item = replacement[0]
    if replacement_item.marker.get("status") != "completed_success":
        raise ValueError("resumed replacement is not successful")
    old_ids = {
        str(record.get("record_id", ""))
        for item in old
        for record in item.records
    }
    marker = replacement_item.marker
    return ResumedReplacementLineage(
        assignment_id=group_id,
        task=str(marker.get("task", "")),
        seed=str(marker.get("seed", "")),
        group_id=group_id,
        role=str(marker.get("role", "")),
        old_failed_attempt_ids=tuple(
            f"{item.marker.get('run_id')}:attempt-{item.marker.get('attempt')}"
            for item in old
        ),
        old_failed_attempt_sha256=tuple(_attempt_evidence_sha(item) for item in old),
        replacement_attempt_id=(
            f"{marker.get('run_id')}:attempt-{marker.get('attempt')}"
        ),
        replacement_attempt_sha256=_attempt_evidence_sha(replacement_item),
        replacement_reason=str(
            continuation_approval.get("approval_statement", "")
        ),
        authorization_id=str(continuation_approval.get("approval_id", "")),
        old_decision_row_count=sum(len(item.records) for item in old),
        old_rows_in_accepted_data=len(old_ids.intersection(effective_record_ids)),
        replacement_decision_row_count=len(replacement_item.records),
        accepted_final_attempt_count=sum(
            item.get("group_id") == group_id for item in outcomes
        ),
        final_status=str(outcome.get("status", "")),
    ).with_id()


def build_runtime_segment_manifest(
    inputs: Round5123AuditInputs,
    *,
    source_identity_resolver: SourceIdentityResolver,
) -> RuntimeSegmentManifest:
    assignments_payload = _load_json(inputs.assignments_path)
    assignments = assignments_payload.get("assignments")
    if not isinstance(assignments, list) or len(assignments) != 60:
        raise ValueError("frozen development assignment manifest must contain 60 units")
    assignments_by_group = {
        str(item["group_id"]): (index, item)
        for index, item in enumerate(assignments)
    }
    if len(assignments_by_group) != 60:
        raise ValueError("frozen development assignments contain duplicate groups")

    effective_status = _load_json(inputs.effective_status_path)
    outcomes = effective_status.get("outcomes")
    if not isinstance(outcomes, list) or len(outcomes) != 60:
        raise ValueError("effective campaign status must contain 60 outcomes")
    selected_run_ids = {str(item.get("selected_run_id", "")) for item in outcomes}
    if len(selected_run_ids) != 60 or "" in selected_run_ids:
        raise ValueError("effective campaign selected run IDs are invalid")

    development_input = _load_json(inputs.development_input_release_path)
    paper_memory = _load_json(inputs.paper_memory_release_path)
    taskset = _load_json(inputs.active_taskset_release_path)
    bootstrap = _load_json(inputs.formal_log_bootstrap_policy_path)
    continuation_manifest = _load_json(inputs.continuation_manifest_path)
    continuation_approval = _load_json(inputs.continuation_approval_path)
    _validate_static_releases(
        development_input=development_input,
        paper_memory=paper_memory,
        taskset=taskset,
        bootstrap=bootstrap,
    )

    all_evidence: list[_AcceptedEvidence] = []
    for root in inputs.campaign_roots:
        all_evidence.extend(
            _accepted_evidence(path)
            for path in sorted(Path(root).glob("runs/*/accepted.json"))
        )
    selected = [
        item for item in all_evidence if item.marker.get("run_id") in selected_run_ids
    ]
    if len(selected) != 60:
        raise ValueError(
            f"selected accepted evidence mismatch: {len(selected)} != 60"
        )
    if len({item.marker.get("run_id") for item in selected}) != 60:
        raise ValueError("selected run has more than one accepted marker")

    train_effective = _load_jsonl(inputs.effective_train_path)
    tune_effective = _load_jsonl(inputs.effective_tune_path)
    effective_records = train_effective + tune_effective
    effective_by_id = {
        str(record.get("record_id", "")): record for record in effective_records
    }
    if len(effective_by_id) != len(effective_records):
        raise ValueError("effective dataset contains duplicate record IDs")
    selected_records = [record for item in selected for record in item.records]
    selected_by_id = {
        str(record.get("record_id", "")): record for record in selected_records
    }
    if set(selected_by_id) != set(effective_by_id):
        raise ValueError("effective dataset does not equal selected decision records")
    if any(
        selected_by_id[record_id].get("record_hash")
        != effective_by_id[record_id].get("record_hash")
        for record_id in selected_by_id
    ):
        raise ValueError("effective dataset altered a selected decision record")

    paper_memory_root = str(paper_memory.get("snapshot_root_sha256", ""))
    segment_units: dict[tuple[str, ...], list[AcceptedUnitBinding]] = defaultdict(list)
    segment_metadata: dict[tuple[str, ...], Mapping[str, Any]] = {}
    receipt_sources: Counter[str] = Counter()
    receipt_source_mismatches = 0
    evidence_by_group: dict[str, list[_AcceptedEvidence]] = defaultdict(list)
    for item in all_evidence:
        evidence_by_group[str(item.marker.get("group_id", ""))].append(item)

    for item in selected:
        _validate_unit_evidence(
            item,
            development_input=development_input,
            paper_memory_root=paper_memory_root,
        )
        marker = item.marker
        group_id = str(marker.get("group_id", ""))
        if group_id not in assignments_by_group:
            raise ValueError(f"accepted unit is absent from frozen order: {group_id}")
        frozen_index, assignment = assignments_by_group[group_id]
        for field in ("role", "task", "seed"):
            if str(marker.get(field, "")) != str(assignment.get(field, "")):
                raise ValueError(f"{group_id}: accepted assignment {field} drift")

        source_commit = str(item.run_binding["source_commit"])
        identity = source_identity_resolver(source_commit)
        key = (
            source_commit,
            str(item.budget_snapshot["snapshot_id"]),
            str(identity["controller_identity_sha256"]),
            str(identity["evaluator_identity_sha256"]),
            str(development_input["prompt_hash_bundle_id"]),
            str(paper_memory["release_id"]),
            str(taskset["release_id"]),
            str(bootstrap["policy_id"]),
        )
        segment_metadata[key] = {
            "identity": identity,
            "budget": item.budget_snapshot,
        }
        segment_units[key].append(
            AcceptedUnitBinding(
                unit_id=group_id,
                role=str(marker["role"]),
                task=str(marker["task"]),
                seed=str(marker["seed"]),
                run_id=str(marker["run_id"]),
                status=str(marker["status"]),
                frozen_order_index=frozen_index,
                legacy_sequence_index=int(assignment["sequence_index"]),
                decision_record_ids=tuple(
                    str(record["record_id"]) for record in item.records
                ),
            )
        )
        receipt_source = str(item.receipt.get("source_commit", ""))
        receipt_sources[receipt_source] += 1
        receipt_source_mismatches += int(receipt_source != source_commit)

    selected_paths = {item.records_path.resolve() for item in selected}
    nonselected_record_ids: set[str] = set()
    for root in inputs.campaign_roots:
        for path in Path(root).glob("runs/*/**/development_decisions.jsonl"):
            if path.resolve() in selected_paths:
                continue
            nonselected_record_ids.update(
                str(record.get("record_id", "")) for record in _load_jsonl(path)
            )
    contamination = len(nonselected_record_ids.intersection(effective_by_id))

    segments: list[RuntimeSegment] = []
    for key, units in segment_units.items():
        metadata = segment_metadata[key]
        identity = metadata["identity"]
        segments.append(
            RuntimeSegment(
                source_commit=key[0],
                controller_identity_sha256=key[2],
                controller_component_sha256=dict(
                    identity["controller_component_sha256"]
                ),
                evaluator_identity_sha256=key[3],
                prompt_hash_bundle_id=key[4],
                paper_memory_v5_release_id=key[5],
                paper_memory_snapshot_root_sha256=paper_memory_root,
                active_taskset_release_id=key[6],
                formal_log_bootstrap_policy_id=key[7],
                execution_budget_profile_id=key[1],
                execution_budget_profile=dict(metadata["budget"]),
                accepted_units=tuple(units),
            ).with_id()
        )

    lineage = _build_replacement_lineage(
        outcomes=outcomes,
        evidence_by_group=evidence_by_group,
        effective_record_ids=set(effective_by_id),
        continuation_approval=continuation_approval,
    )
    warnings = (
        (
            "Legacy bootstrap receipts carry historical source_commit metadata; "
            "runtime identity is bound by run_binding, budget snapshot, decision "
            "records, and source-file hashes."
        ),
        "The accepted development dataset contains multiple runtime segments.",
    )
    manifest = RuntimeSegmentManifest(
        round5122_result_sha=inputs.round5122_result_sha,
        assignment_manifest_id=str(
            continuation_manifest.get("assignment_manifest_id", "")
        ),
        effective_campaign_status_sha256=sha256_file(inputs.effective_status_path),
        effective_train_jsonl_sha256=sha256_file(inputs.effective_train_path),
        effective_tune_jsonl_sha256=sha256_file(inputs.effective_tune_path),
        paper_memory_v5_release_id=str(paper_memory["release_id"]),
        active_taskset_release_id=str(taskset["release_id"]),
        segments=tuple(segments),
        replacement_lineage=lineage,
        failed_attempt_decision_contamination=contamination,
        duplicate_accepted_decision_ids=(
            len(selected_records) - len(selected_by_id)
        ),
        formal_memory_writes=sum(
            int(record.get("formal_memory_write_count", 0))
            for record in effective_records
        ),
        acquisition_store_writes=sum(
            int(record.get("acquisition_write_count", 0))
            for record in effective_records
        ),
        evaluation_chain_calls=sum(
            int(record.get("evaluation_chain_calls", 0))
            for record in effective_records
        ),
        holdout_final_contamination=sum(
            bool(record.get("holdout_accessed"))
            or record.get("role") == "dev_holdout"
            or not bool(record.get("excluded_from_final_evaluation", False))
            for record in effective_records
        ),
        mine_sand_records=sum(
            record.get("task") == "mine sand" for record in effective_records
        ),
        legacy_receipt_source_mismatch_count=receipt_source_mismatches,
        legacy_receipt_source_commits=tuple(sorted(receipt_sources)),
        eligible=True,
        errors=(),
        warnings=warnings,
    ).with_id()
    return manifest


def build_draft_amendment(
    manifest: RuntimeSegmentManifest,
) -> MixedRuntimeDevelopmentAmendment:
    if not manifest.manifest_id:
        manifest = manifest.with_id()
    return MixedRuntimeDevelopmentAmendment(
        amendment_name="DRAFT-round5123-mixed-runtime-development-amendment",
        runtime_segment_manifest_id=manifest.manifest_id,
        status="DRAFT",
        controller_changes_accepted=True,
        budget_relaxations_accepted=True,
        all_final_units_and_records_accepted=True,
        no_outcome_selective_exclusions=True,
        no_unit_removed_by_outcome=True,
        runtime_segment_is_audit_metadata_only=True,
        descriptive_success_rate_is_not_homogeneous_benchmark=True,
        holdout_uses_one_frozen_final_runtime=True,
        no_runtime_change_after_candidate_freeze=True,
    ).with_id()


def write_json_immutable(path: str | Path, value: Mapping[str, Any]) -> None:
    output = Path(path)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite immutable artifact: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
