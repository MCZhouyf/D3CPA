"""Bind a frozen blueprint to memory/confidence/environment artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from dc3pa.reliability.development_protocol import (
    DevelopmentProtocolManifest,
    save_protocol,
)

from .blueprint import RealExperimentBlueprint


BINDING_SCHEMA_VERSION = 1


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def environment_parameter_sha256(parameters: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json(dict(sorted(parameters.items())))
    ).hexdigest()


@dataclass(frozen=True)
class FrozenArtifactBinding:
    binding_name: str
    blueprint_id: str
    memory_snapshot_sha256: str
    memory_snapshot_manifest_id: str
    confidence_artifact_id: str
    confidence_artifact_file_sha256: str
    selected_environment_parameters: Mapping[str, Any]
    environment_parameter_sha256: str
    source_commit: str
    development_protocol_id: str = ""
    schema_version: int = BINDING_SCHEMA_VERSION
    binding_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != BINDING_SCHEMA_VERSION:
            raise ValueError("Unsupported artifact binding schema")
        required = (
            self.binding_name,
            self.blueprint_id,
            self.memory_snapshot_sha256,
            self.memory_snapshot_manifest_id,
            self.confidence_artifact_id,
            self.confidence_artifact_file_sha256,
            self.environment_parameter_sha256,
            self.source_commit,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Artifact binding identifiers are required")
        expected_environment_hash = environment_parameter_sha256(
            self.selected_environment_parameters
        )
        if expected_environment_hash != self.environment_parameter_sha256:
            raise ValueError("Environment parameter hash mismatch")
        expected = self.compute_binding_id()
        if self.binding_id and self.binding_id != expected:
            raise ValueError("Artifact binding hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("binding_id", None)
        payload["selected_environment_parameters"] = dict(
            sorted(self.selected_environment_parameters.items())
        )
        return payload

    def compute_binding_id(self) -> str:
        return hashlib.sha256(_canonical_json(self.payload_without_id())).hexdigest()

    def with_id(self) -> "FrozenArtifactBinding":
        return replace(self, binding_id=self.compute_binding_id())

    def to_dict(self) -> dict[str, Any]:
        binding = self if self.binding_id else self.with_id()
        payload = binding.payload_without_id()
        payload["binding_id"] = binding.binding_id
        return payload


def build_bound_development_protocol(
    *,
    blueprint: RealExperimentBlueprint,
    memory_snapshot_sha256: str,
    confidence_artifact_id: str,
    selected_environment_parameters: Mapping[str, Any],
    protocol_name: str,
    created_from_commit: str,
) -> DevelopmentProtocolManifest:
    blueprint_id = blueprint.blueprint_id or blueprint.compute_blueprint_id()
    if not blueprint.environment_search_space.contains(
        selected_environment_parameters
    ):
        raise ValueError(
            "Selected Environment parameters were not in the frozen search space"
        )
    protocol = DevelopmentProtocolManifest(
        protocol_name=protocol_name,
        assignments=blueprint.development_assignments,
        memory_snapshot_sha256=memory_snapshot_sha256,
        confidence_artifact_id=confidence_artifact_id,
        knowledge_impl="hard_gate_v2",
        model_confidence_impl="ordinal_calibrated",
        environment_impl="topk_v2",
        environment_scope=str(
            selected_environment_parameters["environment_scope"]
        ),
        environment_parameters=dict(selected_environment_parameters),
        created_from_commit=created_from_commit,
        activation_policy_id=blueprint.activation_policy_id,
        notes=(
            f"Generated from immutable real-experiment blueprint {blueprint_id}."
        ),
    ).with_id()
    return protocol


def build_artifact_binding(
    *,
    blueprint: RealExperimentBlueprint,
    memory_snapshot_sha256: str,
    memory_snapshot_manifest_id: str,
    confidence_artifact_id: str,
    confidence_artifact_file_sha256: str,
    selected_environment_parameters: Mapping[str, Any],
    source_commit: str,
    development_protocol_id: str,
    binding_name: str = "dc3pa-real-artifact-binding-v1",
) -> FrozenArtifactBinding:
    blueprint_id = blueprint.blueprint_id or blueprint.compute_blueprint_id()
    if not blueprint.environment_search_space.contains(
        selected_environment_parameters
    ):
        raise ValueError(
            "Selected Environment parameters were not preregistered"
        )
    return FrozenArtifactBinding(
        binding_name=binding_name,
        blueprint_id=blueprint_id,
        memory_snapshot_sha256=memory_snapshot_sha256,
        memory_snapshot_manifest_id=memory_snapshot_manifest_id,
        confidence_artifact_id=confidence_artifact_id,
        confidence_artifact_file_sha256=confidence_artifact_file_sha256,
        selected_environment_parameters=dict(selected_environment_parameters),
        environment_parameter_sha256=environment_parameter_sha256(
            selected_environment_parameters
        ),
        source_commit=source_commit,
        development_protocol_id=development_protocol_id,
    ).with_id()


def save_binding(path: str | Path, binding: FrozenArtifactBinding) -> str:
    binding = binding.with_id()
    output = Path(path)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite binding: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(binding.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return binding.binding_id


def load_binding(path: str | Path) -> FrozenArtifactBinding:
    return FrozenArtifactBinding(
        **json.loads(Path(path).read_text(encoding="utf-8"))
    )
