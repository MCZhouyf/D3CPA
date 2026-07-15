"""Hash-bound manifest for real development runs and paper-facing dry runs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping


RUN_MANIFEST_SCHEMA_VERSION = 1


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True)
class DevelopmentRunManifest:
    run_name: str
    role: str
    source_commit: str
    development_protocol_id: str
    activation_policy_id: str
    final_test_exclusion_id: str
    memory_snapshot_sha256: str
    confidence_artifact_id: str
    environment_parameter_sha256: str
    model_ids: Mapping[str, str]
    prompt_hashes: Mapping[str, str]
    config_hashes: Mapping[str, str]
    budgets: Mapping[str, Any]
    controller_profile: str
    notes: str = ""
    schema_version: int = RUN_MANIFEST_SCHEMA_VERSION
    run_manifest_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != RUN_MANIFEST_SCHEMA_VERSION:
            raise ValueError("Unsupported development run manifest schema")
        required = (
            self.run_name,
            self.role,
            self.source_commit,
            self.development_protocol_id,
            self.activation_policy_id,
            self.final_test_exclusion_id,
            self.memory_snapshot_sha256,
            self.confidence_artifact_id,
            self.environment_parameter_sha256,
            self.controller_profile,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("Development run manifest fields are required")
        expected = self.compute_manifest_id()
        if self.run_manifest_id and self.run_manifest_id != expected:
            raise ValueError("Development run manifest hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("run_manifest_id", None)
        for name in ("model_ids", "prompt_hashes", "config_hashes", "budgets"):
            payload[name] = dict(sorted(payload[name].items()))
        return payload

    def compute_manifest_id(self) -> str:
        return hashlib.sha256(_canonical_json(self.payload_without_id())).hexdigest()

    def with_id(self) -> "DevelopmentRunManifest":
        return replace(self, run_manifest_id=self.compute_manifest_id())

    def to_dict(self) -> dict[str, Any]:
        manifest = self if self.run_manifest_id else self.with_id()
        payload = manifest.payload_without_id()
        payload["run_manifest_id"] = manifest.run_manifest_id
        return payload


def save_development_run_manifest(
    path: str | Path,
    manifest: DevelopmentRunManifest,
) -> str:
    manifest = manifest.with_id()
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest.run_manifest_id
