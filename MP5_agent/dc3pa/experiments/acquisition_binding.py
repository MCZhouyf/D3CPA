"""Provenance binding for successful formal-acquisition memory records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from dc3pa.memory.acquisition import (
    AcquisitionStore,
    LocalSceneCandidate,
    SuccessfulTrajectoryRecord,
)


SCHEMA_VERSION = 1
BINDING_KEY = "formal_acquisition_binding"
PROHIBITED_KEYS = frozenset(
    {
        "chain_of_thought",
        "cot",
        "hidden_reasoning",
        "raw_prompt",
        "prompt_text",
        "response_text",
        "api_key",
        "authorization",
        "openai_key",
    }
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


def _scan_prohibited(value: Any, *, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            current = f"{path}.{key}"
            if normalized in PROHIBITED_KEYS:
                hits.append(current)
            hits.extend(_scan_prohibited(item, path=current))
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for index, item in enumerate(value):
            hits.extend(_scan_prohibited(item, path=f"{path}[{index}]"))
    return hits


@dataclass(frozen=True)
class AcquisitionRecordProvenance:
    campaign_id: str
    schedule_id: str
    formal_authorization_id: str
    execution_tooling_binding_id: str
    episode_index: int
    run_id: str
    attempt_id: str
    stage6_receipt_id: str
    source_commit: str
    blueprint_id: str
    bootstrap_policy_id: str
    bootstrap_amendment_id: str
    bootstrap_data_binding_id: str
    prompt_hash_bundle_id: str
    model_profile_id: str
    requested_model: str
    returned_model_identities: tuple[str, ...]
    task: str
    seed: str
    difficulty: str
    method_id: str
    bootstrap_event_ids: tuple[str, ...]
    injected_log_count: int
    naturally_collected_log_count: int
    natural_completion: bool
    bootstrap_assisted_completion: bool
    planner_calls: int
    reflection_calls: int
    evaluation_chain_calls: int
    trace_sha256: str
    schema_version: int = SCHEMA_VERSION
    provenance_id: str = ""

    def __post_init__(self) -> None:
        required = (
            self.campaign_id,
            self.schedule_id,
            self.formal_authorization_id,
            self.execution_tooling_binding_id,
            self.run_id,
            self.attempt_id,
            self.stage6_receipt_id,
            self.source_commit,
            self.blueprint_id,
            self.bootstrap_policy_id,
            self.bootstrap_amendment_id,
            self.bootstrap_data_binding_id,
            self.prompt_hash_bundle_id,
            self.model_profile_id,
            self.requested_model,
            self.task,
            self.seed,
            self.difficulty,
            self.method_id,
            self.trace_sha256,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Acquisition record provenance is incomplete")
        if self.episode_index < 0:
            raise ValueError("Episode index cannot be negative")
        if not self.returned_model_identities:
            raise ValueError("Returned model identities are required")
        integer_values = (
            self.injected_log_count,
            self.naturally_collected_log_count,
            self.planner_calls,
            self.reflection_calls,
            self.evaluation_chain_calls,
        )
        if any(isinstance(value, bool) or value < 0 for value in integer_values):
            raise ValueError("Provenance counts cannot be negative")
        if self.evaluation_chain_calls != 0:
            raise ValueError("Evaluation Chain must remain disabled")
        if self.natural_completion != (
            not self.bootstrap_event_ids and self.injected_log_count == 0
        ):
            raise ValueError("Natural-completion provenance is inconsistent")
        if self.bootstrap_assisted_completion != bool(
            self.bootstrap_event_ids or self.injected_log_count
        ):
            raise ValueError(
                "Bootstrap-assisted provenance is inconsistent"
            )
        if self.natural_completion == self.bootstrap_assisted_completion:
            raise ValueError("Successful record needs exactly one completion class")
        expected = self.compute_provenance_id()
        if self.provenance_id and self.provenance_id != expected:
            raise ValueError("Provenance hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("provenance_id", None)
        payload["returned_model_identities"] = list(
            self.returned_model_identities
        )
        payload["bootstrap_event_ids"] = list(self.bootstrap_event_ids)
        return payload

    def compute_provenance_id(self) -> str:
        return _sha(self.payload_without_id())

    def with_id(self) -> "AcquisitionRecordProvenance":
        return replace(self, provenance_id=self.compute_provenance_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.provenance_id else self.with_id()
        payload = item.payload_without_id()
        payload["provenance_id"] = item.provenance_id
        return payload


def bind_record_metadata(
    metadata: Mapping[str, Any] | None,
    provenance: AcquisitionRecordProvenance,
) -> dict[str, Any]:
    result = dict(metadata or {})
    if BINDING_KEY in result:
        raise ValueError("Formal acquisition binding already exists")
    result[BINDING_KEY] = provenance.to_dict()
    prohibited = _scan_prohibited(result)
    if prohibited:
        raise ValueError(f"Prohibited metadata fields: {prohibited}")
    return result


def validate_acquisition_payload(
    payload: Mapping[str, Any],
    *,
    expected_campaign_id: str,
    expected_schedule_id: str,
    expected_authorization_id: str,
    expected_tooling_binding_id: str,
    expected_policy_id: str,
    expected_amendment_id: str,
    expected_binding_id: str,
    expected_source_commit: str,
    expected_blueprint_id: str,
) -> AcquisitionRecordProvenance:
    if payload.get("schema_version") not in {1, 2}:
        raise ValueError("Unsupported acquisition payload schema")
    record = payload.get("record")
    if not isinstance(record, Mapping):
        raise ValueError("Acquisition payload has no record object")
    metadata = record.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError("Acquisition record metadata is missing")
    binding = metadata.get(BINDING_KEY)
    if not isinstance(binding, Mapping):
        raise ValueError("Formal acquisition binding is missing")

    normalized = dict(binding)
    normalized["returned_model_identities"] = tuple(
        normalized.get("returned_model_identities", ())
    )
    normalized["bootstrap_event_ids"] = tuple(
        normalized.get("bootstrap_event_ids", ())
    )
    provenance = AcquisitionRecordProvenance(**normalized)

    expected = {
        "campaign_id": expected_campaign_id,
        "schedule_id": expected_schedule_id,
        "formal_authorization_id": expected_authorization_id,
        "execution_tooling_binding_id": expected_tooling_binding_id,
        "bootstrap_policy_id": expected_policy_id,
        "bootstrap_amendment_id": expected_amendment_id,
        "bootstrap_data_binding_id": expected_binding_id,
        "source_commit": expected_source_commit,
        "blueprint_id": expected_blueprint_id,
    }
    mismatches = {
        key: {"actual": getattr(provenance, key), "expected": value}
        for key, value in expected.items()
        if getattr(provenance, key) != value
    }
    if mismatches:
        raise ValueError(f"Acquisition provenance mismatch: {mismatches}")
    if str(record.get("episode_id", "")) != provenance.run_id:
        raise ValueError("Acquisition episode ID must equal the successful run ID")
    if str(record.get("task_name", "")) != provenance.task:
        raise ValueError("Acquisition task name/provenance mismatch")
    if str(record.get("seed", "")) != provenance.seed:
        raise ValueError("Acquisition seed/provenance mismatch")
    candidates = record.get("scene_candidates", ())
    if not isinstance(candidates, Sequence):
        raise ValueError("scene_candidates must be a sequence")
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            raise ValueError(f"scene candidate {index} is not an object")
        if candidate.get("status") != "success":
            raise ValueError("Only successful local actions may enter acquisition")
        if not str(candidate.get("image_path", "")).strip():
            raise ValueError("Scene candidate is missing a pre-action image")
        candidate_metadata = candidate.get("metadata", {})
        if isinstance(candidate_metadata, Mapping):
            if candidate_metadata.get("bootstrap_policy_id") not in (
                None,
                "",
                expected_policy_id,
            ):
                raise ValueError("Scene candidate bootstrap policy mismatch")
    prohibited = _scan_prohibited(payload)
    if prohibited:
        raise ValueError(f"Prohibited acquisition fields: {prohibited}")
    return provenance


def acquisition_root_manifest(root: str | Path) -> dict[str, Any]:
    root_path = Path(root).resolve()
    if not root_path.is_dir():
        raise FileNotFoundError(root_path)
    files = {
        path.relative_to(root_path).as_posix(): sha256_file(path)
        for path in sorted(root_path.rglob("*"))
        if path.is_file()
    }
    return {
        "schema_version": 1,
        "root": ".",
        "file_count": len(files),
        "files": files,
        "root_sha256": _sha(files),
    }


def finalize_staged_acquisition(
    *,
    staging_root: str | Path,
    final_root: str | Path,
    episode_id: str,
    provenance: AcquisitionRecordProvenance,
) -> tuple[Path, dict[str, str]]:
    """Promote one staged success after final trace/receipt IDs are known.

    The destination store is deterministic and refuses divergent replay. The
    staging record is retained so a crash can be reconciled without rerunning
    Minecraft.
    """
    staging = Path(staging_root).resolve()
    payload_path = AcquisitionStore(staging).episode_path(episode_id)
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    record = payload.get("record")
    if not isinstance(record, Mapping):
        raise ValueError("Staged acquisition payload has no record")
    if str(record.get("episode_id", "")) != episode_id:
        raise ValueError("Staged acquisition episode ID mismatch")

    final_store = AcquisitionStore(final_root)
    candidates: list[LocalSceneCandidate] = []
    image_hashes: dict[str, str] = {}
    image_path_map: dict[str, str] = {}
    for raw in record.get("scene_candidates", ()):
        if not isinstance(raw, Mapping) or raw.get("status") != "success":
            raise ValueError("Staged record contains a non-success Scene candidate")
        relative = str(raw.get("image_path", ""))
        source = (staging / relative).resolve()
        try:
            source.relative_to(staging)
        except ValueError as exc:
            raise ValueError("Staged image escapes acquisition root") from exc
        if not source.is_file():
            raise FileNotFoundError(source)
        import numpy as np

        rgb = np.load(source, allow_pickle=False)
        final_relative = final_store.write_rgb_array(
            episode_id=episode_id,
            step_id=str(raw.get("step_id", "")),
            action_index=int(raw.get("action_index", -1)),
            rgb=rgb,
        )
        image_path_map[relative] = final_relative
        final_path = Path(final_root).resolve() / final_relative
        image_hashes[final_relative] = sha256_file(final_path)
        metadata = dict(raw.get("metadata", {}))
        metadata[BINDING_KEY] = provenance.to_dict()
        metadata["image_sha256"] = image_hashes[final_relative]
        candidates.append(
            LocalSceneCandidate(
                episode_id=episode_id,
                task_name=provenance.task,
                plan_id=str(raw.get("plan_id", "")),
                plan_version=int(raw.get("plan_version", 0)),
                step_id=str(raw.get("step_id", "")),
                step_index=int(raw.get("step_index", -1)),
                action_index=int(raw.get("action_index", -1)),
                local_subgoal=str(raw.get("local_subgoal", "")),
                action=dict(raw.get("action", {})),
                image_path=final_relative,
                pre_inventory=dict(raw.get("pre_inventory", {})),
                status="success",
                metadata=metadata,
            )
        )

    telemetry = []
    for item in record.get("telemetry", ()):
        normalized = dict(item)
        old_path = str(normalized.get("image_path", ""))
        if old_path in image_path_map:
            normalized["image_path"] = image_path_map[old_path]
        telemetry.append(normalized)
    metadata = bind_record_metadata(record.get("metadata", {}), provenance)
    final_record = SuccessfulTrajectoryRecord(
        episode_id=episode_id,
        task_name=provenance.task,
        seed=provenance.seed,
        plan=dict(record.get("plan", {})),
        telemetry=tuple(telemetry),
        scene_candidates=tuple(candidates),
        metadata=metadata,
    )
    target = final_store.commit_success(final_record)
    persisted = json.loads(target.read_text(encoding="utf-8"))
    validate_acquisition_payload(
        persisted,
        expected_campaign_id=provenance.campaign_id,
        expected_schedule_id=provenance.schedule_id,
        expected_authorization_id=provenance.formal_authorization_id,
        expected_tooling_binding_id=provenance.execution_tooling_binding_id,
        expected_policy_id=provenance.bootstrap_policy_id,
        expected_amendment_id=provenance.bootstrap_amendment_id,
        expected_binding_id=provenance.bootstrap_data_binding_id,
        expected_source_commit=provenance.source_commit,
        expected_blueprint_id=provenance.blueprint_id,
    )
    return target, image_hashes
