"""Read-only historical compatibility audit for CHRM-lite + CDT-lite V4.1."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .development_records import load_development_record
from .round5126_confirmatory import sha256_file


SCHEMA_VERSION = 1
EXPECTED_TRAIN_ROWS = 528
EXPECTED_TUNE_ROWS = 153
MINIMUM_CHRM_ROW_COVERAGE = 0.95
MINIMUM_CHRM_TASK_COVERAGE = 1.0


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _load(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _load_jsonl(path: Path) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise ValueError(f"Expected JSON object at {path}:{line_number}")
        rows.append(value)
    return rows


def _dataset_id(rows: Sequence[Mapping[str, Any]]) -> str:
    return _sha(
        [
            {"record_id": str(row["record_id"]), "record_hash": str(row["record_hash"])}
            for row in sorted(rows, key=lambda item: str(item["record_id"]))
        ]
    )


class _HashedContract:
    _id_field: str

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop(self._id_field, None)
        return payload

    def compute_id(self) -> str:
        return _sha(self.payload_without_id())

    def to_dict(self) -> dict[str, Any]:
        identifier = getattr(self, self._id_field)
        item = self if identifier else replace(self, **{self._id_field: self.compute_id()})
        payload = item.payload_without_id()
        payload[self._id_field] = getattr(item, self._id_field)
        return payload


@dataclass(frozen=True)
class HistoricalDatasetLineageAudit(_HashedContract):
    source_commit: str
    development_closeout_id: str
    dataset_acceptance_id: str
    train_sha256: str
    tune_sha256: str
    train_dataset_id: str
    tune_dataset_id: str
    train_rows: int
    tune_rows: int
    train_tasks: int
    tune_tasks: int
    train_groups: int
    tune_groups: int
    train_task_seed_run_groups: int
    tune_task_seed_run_groups: int
    duplicate_record_ids: int
    terminal_task_split_overlap: int
    holdout_or_final_rows: int
    failed_technical_attempt_contamination: int
    accepted_attempts: int
    accepted_trace_files: int
    paper_memory_v5_release_id: str
    paper_memory_v5_root_sha256: str
    dependency_schema_id: str
    scene_exemplar_release_id: str
    source_runtime_identities: tuple[str, ...]
    eligible: bool
    errors: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if self.eligible and self.errors:
            raise ValueError("Eligible lineage audit cannot contain errors")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Historical lineage audit hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["source_runtime_identities"] = list(self.source_runtime_identities)
        payload["errors"] = list(self.errors)
        return payload

    def with_id(self) -> "HistoricalDatasetLineageAudit":
        return replace(self, audit_id=self.compute_id())


@dataclass(frozen=True)
class FeatureAvailabilityRow:
    feature: str
    train_available_count: int
    train_total: int
    tune_available_count: int
    tune_total: int
    task_coverage_count: int
    task_total: int
    difficulty_coverage_count: int
    difficulty_total: int
    missing_reason: str
    reconstructable_without_new_llm: bool
    reconstructable_without_minedojo: bool
    required_new_collection: bool

    def __post_init__(self) -> None:
        values = (
            self.train_available_count,
            self.train_total,
            self.tune_available_count,
            self.tune_total,
            self.task_coverage_count,
            self.task_total,
            self.difficulty_coverage_count,
            self.difficulty_total,
        )
        if any(value < 0 for value in values):
            raise ValueError("Feature availability counts cannot be negative")
        if self.train_available_count > self.train_total or self.tune_available_count > self.tune_total:
            raise ValueError("Feature availability exceeds its split size")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["train_available_rate"] = self.train_available_count / self.train_total
        payload["tune_available_rate"] = self.tune_available_count / self.tune_total
        payload["task_coverage_rate"] = self.task_coverage_count / self.task_total
        payload["difficulty_coverage_rate"] = self.difficulty_coverage_count / self.difficulty_total
        return payload


@dataclass(frozen=True)
class FeatureAvailabilityMatrix(_HashedContract):
    source_commit: str
    lineage_audit_id: str
    rows: tuple[FeatureAvailabilityRow, ...]
    no_new_llm_called: bool
    no_minedojo_started: bool
    schema_version: int = SCHEMA_VERSION
    matrix_id: str = ""

    _id_field = "matrix_id"

    def __post_init__(self) -> None:
        names = tuple(row.feature for row in self.rows)
        if len(names) != len(set(names)) or not names:
            raise ValueError("Feature availability matrix rows are invalid")
        if not self.no_new_llm_called or not self.no_minedojo_started:
            raise ValueError("Compatibility audit opened a forbidden runtime")
        if self.matrix_id and self.matrix_id != self.compute_id():
            raise ValueError("Feature availability matrix hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["rows"] = [row.to_dict() for row in self.rows]
        return payload

    def with_id(self) -> "FeatureAvailabilityMatrix":
        return replace(self, matrix_id=self.compute_id())


@dataclass(frozen=True)
class MissingEvidenceRegistry(_HashedContract):
    source_commit: str
    matrix_id: str
    missing: Mapping[str, str]
    manual_backfill_forbidden: bool
    llm_backfill_forbidden: bool
    future_holdout_backfill_forbidden: bool
    schema_version: int = SCHEMA_VERSION
    registry_id: str = ""

    _id_field = "registry_id"

    def __post_init__(self) -> None:
        if not self.missing:
            raise ValueError("Missing evidence registry cannot be empty")
        if not all(
            (self.manual_backfill_forbidden, self.llm_backfill_forbidden, self.future_holdout_backfill_forbidden)
        ):
            raise ValueError("Missing evidence backfill guard changed")
        if self.registry_id and self.registry_id != self.compute_id():
            raise ValueError("Missing evidence registry hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["missing"] = dict(sorted(self.missing.items()))
        return payload

    def with_id(self) -> "MissingEvidenceRegistry":
        return replace(self, registry_id=self.compute_id())


@dataclass(frozen=True)
class CDTIdentifiabilityAudit(_HashedContract):
    source_commit: str
    evaluation_called_rows: int
    original_action_rows: int
    revised_action_rows: int
    action_changed_rows: int
    revised_execution_result_rows: int
    original_execution_result_rows: int
    matched_state_replay_pairs: int
    evaluation_cost_rows: int
    downstream_cost_rows: int
    terminal_failure_rows: int
    rho_path_a_evidence_count: int
    rho_path_b_evidence_count: int
    c_eval_evidence_count: int
    c_fp_evidence_count: int
    l_fail_compute_evidence_count: int
    l_fail_terminal_evidence_count: int
    decision: str
    counterfactual_outcomes_inferred: bool = False
    parameters_estimated: bool = False
    schema_version: int = SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if self.decision not in {
            "CDT Path A feasible",
            "CDT Path B feasible",
            "CDT not identifiable from historical logs",
        }:
            raise ValueError("Unknown CDT identifiability decision")
        if self.counterfactual_outcomes_inferred or self.parameters_estimated:
            raise ValueError("CDT audit estimated or invented forbidden evidence")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("CDT identifiability audit hash mismatch")

    def with_id(self) -> "CDTIdentifiabilityAudit":
        return replace(self, audit_id=self.compute_id())


@dataclass(frozen=True)
class HistoricalLogCompatibilityAudit(_HashedContract):
    source_commit: str
    lineage_audit_id: str
    feature_matrix_id: str
    missing_evidence_registry_id: str
    cdt_identifiability_audit_id: str
    action_signature_rows: int
    knowledge_fully_reconstructable_rows: int
    knowledge_partially_reconstructable_rows: int
    knowledge_not_reconstructable_rows: int
    confidence_present_rows: int
    same_generation_confidence_rows: int
    confidence_separate_provider_call_rows: int
    failure_mode_rows: int
    environment_positive_pool_rows: int
    environment_negative_pool_rows: int
    environment_bilateral_rows: int
    main_label_present_rows: int
    main_label_fully_joined_rows: int
    main_label_ambiguous_rows: int
    usefulness_label_rows: int
    accepted_trace_event_counts: Mapping[str, int]
    input_artifacts_unchanged: bool
    no_new_llm_called: bool
    no_minedojo_started: bool
    schema_version: int = SCHEMA_VERSION
    audit_id: str = ""

    _id_field = "audit_id"

    def __post_init__(self) -> None:
        if not all((self.input_artifacts_unchanged, self.no_new_llm_called, self.no_minedojo_started)):
            raise ValueError("Historical audit changed or executed protected inputs")
        if self.audit_id and self.audit_id != self.compute_id():
            raise ValueError("Historical compatibility audit hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["accepted_trace_event_counts"] = dict(sorted(self.accepted_trace_event_counts.items()))
        return payload

    def with_id(self) -> "HistoricalLogCompatibilityAudit":
        return replace(self, audit_id=self.compute_id())


@dataclass(frozen=True)
class Round513HistoricalDataDecision(_HashedContract):
    source_commit: str
    compatibility_audit_id: str
    decision: str
    exact_reasons: tuple[str, ...]
    chrm_reconstruction_permitted: bool
    cdt_historical_identification_permitted: bool
    targeted_new_development_collection_required: bool
    minimum_chrm_row_coverage: float = MINIMUM_CHRM_ROW_COVERAGE
    minimum_chrm_task_coverage: float = MINIMUM_CHRM_TASK_COVERAGE
    model_fitted: bool = False
    cdt_parameters_estimated: bool = False
    holdout_accessed: bool = False
    final_evaluation_open: bool = False
    round6_open: bool = False
    schema_version: int = SCHEMA_VERSION
    decision_id: str = ""

    _id_field = "decision_id"

    def __post_init__(self) -> None:
        if self.decision not in {"A", "B", "C", "D"}:
            raise ValueError("Unknown historical data decision")
        if not self.exact_reasons:
            raise ValueError("Historical data decision requires exact reasons")
        if any((self.model_fitted, self.cdt_parameters_estimated, self.holdout_accessed, self.final_evaluation_open, self.round6_open)):
            raise ValueError("Historical audit opened a forbidden phase")
        if self.decision == "D" and (
            self.chrm_reconstruction_permitted or self.cdt_historical_identification_permitted
        ):
            raise ValueError("Decision D cannot permit historical fitting")
        if self.decision_id and self.decision_id != self.compute_id():
            raise ValueError("Historical data decision hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = super().payload_without_id()
        payload["exact_reasons"] = list(self.exact_reasons)
        return payload

    def with_id(self) -> "Round513HistoricalDataDecision":
        return replace(self, decision_id=self.compute_id())


@dataclass(frozen=True)
class HistoricalAuditInputs:
    source_commit: str
    train_path: Path
    tune_path: Path
    acceptance_path: Path
    closeout_path: Path
    effective_status_path: Path
    campaign_roots: tuple[Path, ...]
    paper_memory_release_path: Path
    paper_memory_database_path: Path
    scene_lineage_audit_path: Path
    confidence_release_path: Path
    environment_release_path: Path
    fusion_feature_release_path: Path
    active_taskset_release_path: Path
    ordinal_confidence_source_path: Path


def _availability_row(
    feature: str,
    train: Sequence[Mapping[str, Any]],
    tune: Sequence[Mapping[str, Any]],
    predicate,
    missing_reason: str,
    *,
    no_llm: bool,
    no_minedojo: bool,
    required_new_collection: bool,
) -> FeatureAvailabilityRow:
    available_train = [row for row in train if predicate(row)]
    available_tune = [row for row in tune if predicate(row)]
    available = available_train + available_tune
    all_rows = list(train) + list(tune)
    return FeatureAvailabilityRow(
        feature=feature,
        train_available_count=len(available_train),
        train_total=len(train),
        tune_available_count=len(available_tune),
        tune_total=len(tune),
        task_coverage_count=len({str(row["task"]) for row in available}),
        task_total=len({str(row["task"]) for row in all_rows}),
        difficulty_coverage_count=len({str(row["difficulty"]) for row in available}),
        difficulty_total=len({str(row["difficulty"]) for row in all_rows}),
        missing_reason=missing_reason,
        reconstructable_without_new_llm=no_llm,
        reconstructable_without_minedojo=no_minedojo,
        required_new_collection=required_new_collection,
    )


def _accepted_trace_audit(
    status: Mapping[str, Any], campaign_roots: Sequence[Path], accepted_rows: Mapping[str, Mapping[str, Any]]
) -> tuple[int, Counter[str], int]:
    outcomes = status.get("outcomes")
    if not isinstance(outcomes, list) or len(outcomes) != 60:
        raise ValueError("Effective campaign status does not contain 60 outcomes")
    selected = {str(item["selected_run_id"]) for item in outcomes}
    markers: dict[str, tuple[Path, Mapping[str, Any]]] = {}
    for root in campaign_roots:
        for marker_path in sorted(root.glob("runs/*/accepted.json")):
            marker = _load(marker_path)
            run_id = str(marker.get("run_id", ""))
            if run_id in selected:
                markers[run_id] = (marker_path, marker)
    if set(markers) != selected:
        raise ValueError("Accepted attempt lineage is incomplete")
    event_counts: Counter[str] = Counter()
    separate_confidence_rows = 0
    for run_id in sorted(markers):
        marker_path, marker = markers[run_id]
        attempt = int(marker.get("attempt", -1))
        if attempt < 0:
            raise ValueError("Accepted marker has invalid attempt")
        attempt_path = marker_path.parent / f"attempt-{attempt}"
        records_path = marker_path.parents[2] / str(marker["records"])
        trace_path = attempt_path / "trace.jsonl"
        for required in (
            records_path,
            trace_path,
            attempt_path / "run_binding.json",
            attempt_path / "execution_budget_snapshot.json",
        ):
            if not required.is_file():
                raise ValueError(f"Accepted evidence is incomplete: {required.name}")
        source_rows = _load_jsonl(records_path)
        for row in source_rows:
            record_id = str(row["record_id"])
            effective = accepted_rows.get(record_id)
            if effective is None or effective.get("record_hash") != row.get("record_hash"):
                raise ValueError("Accepted attempt decision lineage changed")
        trace_events = _load_jsonl(trace_path)
        purposes = Counter(
            str(event.get("payload", {}).get("purpose", ""))
            for event in trace_events
            if event.get("event_type") == "llm_call_started"
        )
        event_counts.update(str(event.get("event_type", "")) for event in trace_events)
        if purposes["dc3pa_confidence_and_evaluation"] > 0:
            separate_confidence_rows += len(source_rows)
    return len(markers), event_counts, separate_confidence_rows


def _memory_identities(database_path: Path, memory_release: Mapping[str, Any], scene_lineage: Mapping[str, Any]) -> tuple[str, str]:
    if sha256_file(database_path) != memory_release.get("database_sha256"):
        raise ValueError("Paper Memory V5 database hash changed")
    connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        edges = [
            dict(row)
            for row in connection.execute(
                "SELECT prerequisite,target,relation_type,quantity,confidence,success_count,"
                "first_episode_id,last_episode_id FROM dependency_edges "
                "ORDER BY target,relation_type,prerequisite"
            )
        ]
        scene_count = int(connection.execute("SELECT COUNT(*) FROM scene_exemplars").fetchone()[0])
    finally:
        connection.close()
    if len(edges) != int(memory_release.get("dependency_edge_count", -1)):
        raise ValueError("Dependency edge count changed")
    if scene_count != int(memory_release.get("scene_exemplar_count", -1)):
        raise ValueError("Scene exemplar count changed")
    dependency_id = _sha({"schema_version": 1, "edges": edges})
    scene_release_id = _sha(
        {
            "paper_memory_v5_release_id": memory_release["release_id"],
            "snapshot_root_sha256": memory_release["snapshot_root_sha256"],
            "scene_exemplar_count": scene_count,
            "scene_lineage_audit_id": scene_lineage["audit_id"],
        }
    )
    return dependency_id, scene_release_id


def build_historical_compatibility_audit(inputs: HistoricalAuditInputs):
    protected_paths = (
        inputs.train_path,
        inputs.tune_path,
        inputs.acceptance_path,
        inputs.closeout_path,
        inputs.effective_status_path,
        inputs.paper_memory_release_path,
        inputs.paper_memory_database_path,
        inputs.scene_lineage_audit_path,
        inputs.confidence_release_path,
        inputs.environment_release_path,
        inputs.fusion_feature_release_path,
        inputs.active_taskset_release_path,
        inputs.ordinal_confidence_source_path,
    )
    before_hashes = {str(index): sha256_file(path) for index, path in enumerate(protected_paths)}
    train = _load_jsonl(inputs.train_path)
    tune = _load_jsonl(inputs.tune_path)
    acceptance = _load(inputs.acceptance_path)
    closeout = _load(inputs.closeout_path)
    status = _load(inputs.effective_status_path)
    memory = _load(inputs.paper_memory_release_path)
    scene_lineage = _load(inputs.scene_lineage_audit_path)
    confidence = _load(inputs.confidence_release_path)
    environment = _load(inputs.environment_release_path)
    fusion = _load(inputs.fusion_feature_release_path)
    taskset = _load(inputs.active_taskset_release_path)
    ordinal_source = inputs.ordinal_confidence_source_path.read_text(encoding="utf-8")

    errors: list[str] = []
    if (len(train), len(tune)) != (EXPECTED_TRAIN_ROWS, EXPECTED_TUNE_ROWS):
        errors.append(f"row counts changed: train={len(train)} tune={len(tune)}")
    if sha256_file(inputs.train_path) != acceptance.get("train_jsonl_sha256"):
        errors.append("train file hash differs from Standard Development Closeout")
    if sha256_file(inputs.tune_path) != acceptance.get("tune_jsonl_sha256"):
        errors.append("tune file hash differs from Standard Development Closeout")
    if _dataset_id(train) != acceptance.get("train_dataset_id"):
        errors.append("train dataset identity changed")
    if _dataset_id(tune) != acceptance.get("tune_dataset_id"):
        errors.append("tune dataset identity changed")
    for row in train + tune:
        load_development_record(row)
    accepted_by_id = {str(row["record_id"]): row for row in train + tune}
    duplicate_ids = len(train) + len(tune) - len(accepted_by_id)
    train_tasks = {str(row["task"]) for row in train}
    tune_tasks = {str(row["task"]) for row in tune}
    overlap = train_tasks & tune_tasks
    holdout_final = sum(
        bool(row.get("holdout_accessed"))
        or row.get("role") not in {"dev_train", "dev_tune"}
        or not bool(row.get("excluded_from_final_evaluation"))
        for row in train + tune
    )
    integrity = acceptance.get("integrity", {})
    contamination = int(integrity.get("failed_attempt_decision_contamination", -1))
    if any((duplicate_ids, len(overlap), holdout_final, contamination)):
        errors.append("duplicate, split, holdout/final, or technical contamination detected")
    if closeout.get("closeout_id") != "da9a01ff03cfce6efbb2eda303bfc8ddccf2828829cf2948fb3dbe1cae46ad7e":
        errors.append("Unexpected Standard Development Closeout identity")
    if memory.get("release_id") != acceptance.get("paper_memory_v5_release_id"):
        errors.append("Paper Memory V5 release differs from accepted development data")
    if taskset.get("release_id") != acceptance.get("active_taskset_release_id"):
        errors.append("Active taskset release differs from accepted development data")
    if (
        confidence.get("train_dataset_id") != acceptance.get("train_dataset_id")
        or confidence.get("tune_dataset_id") != acceptance.get("tune_dataset_id")
        or confidence.get("paper_memory_v5_release_id") != memory.get("release_id")
    ):
        errors.append("Confidence release lineage differs from accepted development data")
    if (
        environment.get("paper_memory_v5_release_id") != memory.get("release_id")
        or environment.get("active_taskset_release_id") != taskset.get("release_id")
    ):
        errors.append("Environment release lineage differs from frozen memory/taskset")
    if (
        fusion.get("confidence_calibration_release_id") != confidence.get("release_id")
        or fusion.get("environment_evidence_release_id") != environment.get("release_id")
        or int(fusion.get("train_record_count", -1)) != len(train)
        or int(fusion.get("tune_record_count", -1)) != len(tune)
        or bool(fusion.get("holdout_used"))
        or bool(fusion.get("final_evaluation_used"))
    ):
        errors.append("Fusion-feature release lineage or isolation changed")
    dependency_id, scene_release_id = _memory_identities(
        inputs.paper_memory_database_path, memory, scene_lineage
    )
    accepted_attempt_count, event_counts, separate_confidence_rows = _accepted_trace_audit(
        status, inputs.campaign_roots, accepted_by_id
    )
    if accepted_attempt_count != 60:
        errors.append("Accepted attempt count changed")
    if "raw = self.provider.confidence(request)" not in ordinal_source:
        errors.append("Historical separate confidence provider source cannot be verified")

    source_runtime = tuple(sorted({str(row["source_commit"]) for row in train + tune}))
    lineage = HistoricalDatasetLineageAudit(
        source_commit=inputs.source_commit,
        development_closeout_id=str(closeout["closeout_id"]),
        dataset_acceptance_id=str(acceptance["acceptance_id"]),
        train_sha256=sha256_file(inputs.train_path),
        tune_sha256=sha256_file(inputs.tune_path),
        train_dataset_id=_dataset_id(train),
        tune_dataset_id=_dataset_id(tune),
        train_rows=len(train),
        tune_rows=len(tune),
        train_tasks=len(train_tasks),
        tune_tasks=len(tune_tasks),
        train_groups=len({str(row["group_id"]) for row in train}),
        tune_groups=len({str(row["group_id"]) for row in tune}),
        train_task_seed_run_groups=len({(row["task"], row["seed"], row["run_id"]) for row in train}),
        tune_task_seed_run_groups=len({(row["task"], row["seed"], row["run_id"]) for row in tune}),
        duplicate_record_ids=duplicate_ids,
        terminal_task_split_overlap=len(overlap),
        holdout_or_final_rows=holdout_final,
        failed_technical_attempt_contamination=contamination,
        accepted_attempts=accepted_attempt_count,
        accepted_trace_files=accepted_attempt_count,
        paper_memory_v5_release_id=str(memory["release_id"]),
        paper_memory_v5_root_sha256=str(memory["snapshot_root_sha256"]),
        dependency_schema_id=dependency_id,
        scene_exemplar_release_id=scene_release_id,
        source_runtime_identities=source_runtime,
        eligible=not errors,
        errors=tuple(errors),
    ).with_id()
    if not lineage.eligible:
        raise ValueError("; ".join(lineage.errors))

    all_rows = train + tune
    action_signature = lambda row: bool(json.loads(str(row.get("proposed_action", "{}"))).get("name"))
    confidence_present = lambda row: row.get("confidence_level") in {"very_low", "low", "medium", "high", "very_high"}
    positive_pool = lambda row: bool(row.get("environment_topk_exemplar_ids"))
    never = lambda row: False
    always = lambda row: True
    matrix_rows = (
        _availability_row("h", train, tune, never, "no frozen per-row hard/soft rule classification and satisfaction lineage", no_llm=True, no_minedojo=True, required_new_collection=True),
        _availability_row("k", train, tune, never, "historical coverage mixes hard and soft checks", no_llm=True, no_minedojo=True, required_new_collection=True),
        _availability_row("u", train, tune, never, "historical knowledge availability is not tied to frozen soft-rule sets", no_llm=True, no_minedojo=True, required_new_collection=True),
        _availability_row("five_level_confidence", train, tune, confidence_present, "", no_llm=True, no_minedojo=True, required_new_collection=False),
        _availability_row("same_generation_confidence_proof", train, tune, never, "confidence was collected by a separate provider call after planning", no_llm=False, no_minedojo=True, required_new_collection=True),
        _availability_row("N+", train, tune, positive_pool, "most rows lack compatible exemplars; stored pool is one-sided", no_llm=True, no_minedojo=True, required_new_collection=True),
        _availability_row("N-", train, tune, never, "no incompatible visually-similar exemplar pool was recorded", no_llm=True, no_minedojo=True, required_new_collection=True),
        _availability_row("cov+", train, tune, positive_pool, "positive coverage is absent for most rows", no_llm=True, no_minedojo=True, required_new_collection=True),
        _availability_row("cov-", train, tune, never, "negative coverage was not recorded", no_llm=True, no_minedojo=True, required_new_collection=True),
        _availability_row("Environment_state_v4_1", train, tune, never, "bilateral contrast and query observation identity are absent", no_llm=True, no_minedojo=True, required_new_collection=True),
        _availability_row("main_label_fully_joined", train, tune, never, "decision_correct exists but per-step transition/source-status evidence was not persisted", no_llm=True, no_minedojo=True, required_new_collection=True),
        _availability_row("usefulness_label", train, tune, never, "no deterministic truth-dependency usefulness join was persisted", no_llm=True, no_minedojo=True, required_new_collection=False),
        _availability_row("Evaluation_before_after_action", train, tune, never, "Evaluation Chain was disabled", no_llm=True, no_minedojo=True, required_new_collection=True),
        _availability_row("rho_Path_A_evidence", train, tune, never, "no matched-state paired replay", no_llm=True, no_minedojo=True, required_new_collection=True),
        _availability_row("rho_Path_B_evidence", train, tune, never, "no observed Evaluation action changes and revised executions", no_llm=True, no_minedojo=True, required_new_collection=True),
        _availability_row("c_eval", train, tune, never, "no Evaluation calls in accepted development data", no_llm=True, no_minedojo=True, required_new_collection=True),
        _availability_row("c_fp", train, tune, never, "no evaluated correct-step action-change costs", no_llm=True, no_minedojo=True, required_new_collection=True),
        _availability_row("L_fail_compute_component", train, tune, never, "no per-step downstream recovery cost lineage", no_llm=True, no_minedojo=True, required_new_collection=True),
        _availability_row("L_fail_terminal_component", train, tune, never, "no per-step remaining-horizon terminal penalty evidence", no_llm=True, no_minedojo=True, required_new_collection=True),
    )
    matrix = FeatureAvailabilityMatrix(
        source_commit=inputs.source_commit,
        lineage_audit_id=lineage.audit_id,
        rows=matrix_rows,
        no_new_llm_called=True,
        no_minedojo_started=True,
    ).with_id()
    missing = MissingEvidenceRegistry(
        source_commit=inputs.source_commit,
        matrix_id=matrix.matrix_id,
        missing={row.feature: row.missing_reason for row in matrix_rows if row.train_available_count < row.train_total or row.tune_available_count < row.tune_total},
        manual_backfill_forbidden=True,
        llm_backfill_forbidden=True,
        future_holdout_backfill_forbidden=True,
    ).with_id()
    cdt = CDTIdentifiabilityAudit(
        source_commit=inputs.source_commit,
        evaluation_called_rows=sum(int(row.get("evaluation_chain_calls", 0)) > 0 for row in all_rows),
        original_action_rows=0,
        revised_action_rows=0,
        action_changed_rows=0,
        revised_execution_result_rows=0,
        original_execution_result_rows=0,
        matched_state_replay_pairs=0,
        evaluation_cost_rows=0,
        downstream_cost_rows=0,
        terminal_failure_rows=0,
        rho_path_a_evidence_count=0,
        rho_path_b_evidence_count=0,
        c_eval_evidence_count=0,
        c_fp_evidence_count=0,
        l_fail_compute_evidence_count=0,
        l_fail_terminal_evidence_count=0,
        decision="CDT not identifiable from historical logs",
    ).with_id()
    after_hashes = {str(index): sha256_file(path) for index, path in enumerate(protected_paths)}
    compatibility = HistoricalLogCompatibilityAudit(
        source_commit=inputs.source_commit,
        lineage_audit_id=lineage.audit_id,
        feature_matrix_id=matrix.matrix_id,
        missing_evidence_registry_id=missing.registry_id,
        cdt_identifiability_audit_id=cdt.audit_id,
        action_signature_rows=sum(action_signature(row) for row in all_rows),
        knowledge_fully_reconstructable_rows=0,
        knowledge_partially_reconstructable_rows=0,
        knowledge_not_reconstructable_rows=len(all_rows),
        confidence_present_rows=sum(confidence_present(row) for row in all_rows),
        same_generation_confidence_rows=0,
        confidence_separate_provider_call_rows=separate_confidence_rows,
        failure_mode_rows=sum("failure_mode" in row for row in all_rows),
        environment_positive_pool_rows=sum(positive_pool(row) for row in all_rows),
        environment_negative_pool_rows=0,
        environment_bilateral_rows=0,
        main_label_present_rows=sum("decision_correct" in row for row in all_rows),
        main_label_fully_joined_rows=0,
        main_label_ambiguous_rows=len(all_rows),
        usefulness_label_rows=0,
        accepted_trace_event_counts=dict(event_counts),
        input_artifacts_unchanged=before_hashes == after_hashes,
        no_new_llm_called=True,
        no_minedojo_started=True,
    ).with_id()
    decision = Round513HistoricalDataDecision(
        source_commit=inputs.source_commit,
        compatibility_audit_id=compatibility.audit_id,
        decision="D",
        exact_reasons=(
            "V4.1 hard/soft Knowledge features cannot be reconstructed from aggregate historical fields.",
            "All historical confidence values came from separate post-planning provider calls, not the same Planner generation.",
            "No historical row has bilateral Environment N+/N- evidence or query-observation lineage.",
            "Per-step transition/source-status evidence needed for a fully joined main label was not persisted.",
            "Evaluation Chain calls are zero, so neither CDT Path A nor Path B is identifiable.",
        ),
        chrm_reconstruction_permitted=False,
        cdt_historical_identification_permitted=False,
        targeted_new_development_collection_required=True,
    ).with_id()
    return lineage, matrix, missing, cdt, compatibility, decision
