"""Pre-registered development protocol for unbiased fusion activation.

The protocol is deliberately separate from measured outcomes. It records the
task/seed group assignment, fixed evidence configuration, activation policy
hash, and artifact bindings before holdout labels are inspected.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


PROTOCOL_SCHEMA_VERSION = 2
DEVELOPMENT_ROLES = frozenset({"dev_train", "dev_tune", "dev_holdout"})
DEVELOPMENT_GOAL_STATUSES = frozenset(
    {"experience_covered", "development_novel_goal"}
)
LEGACY_GOAL_STATUSES = frozenset({"held_out_terminal_goal"})


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class GroupAssignment:
    group_id: str
    task: str
    seed: str
    role: str
    difficulty: str = ""
    goal_status: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.group_id.strip():
            raise ValueError("group_id is required")
        if not self.task.strip():
            raise ValueError("task is required")
        if not self.seed.strip():
            raise ValueError("seed is required")
        if self.role not in DEVELOPMENT_ROLES:
            raise ValueError(
                f"role must be one of {sorted(DEVELOPMENT_ROLES)}, got {self.role!r}"
            )
        if (
            self.goal_status
            and self.goal_status not in DEVELOPMENT_GOAL_STATUSES | LEGACY_GOAL_STATUSES
        ):
            raise ValueError("Unknown goal_status")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True)
class DevelopmentProtocolManifest:
    protocol_name: str
    assignments: tuple[GroupAssignment, ...]
    memory_snapshot_sha256: str
    confidence_artifact_id: str
    knowledge_impl: str
    model_confidence_impl: str
    environment_impl: str
    environment_scope: str
    environment_parameters: Mapping[str, Any]
    created_from_commit: str
    activation_policy_id: str = ""
    notes: str = ""
    schema_version: int = PROTOCOL_SCHEMA_VERSION
    protocol_id: str = ""
    activation_policy_sha256: str = ""

    def __post_init__(self) -> None:
        if self.schema_version not in {1, PROTOCOL_SCHEMA_VERSION}:
            raise ValueError("Unsupported protocol schema")
        policy_id = self.semantic_activation_policy_id()
        required = {
            "protocol_name": self.protocol_name,
            "memory_snapshot_sha256": self.memory_snapshot_sha256,
            "confidence_artifact_id": self.confidence_artifact_id,
            "knowledge_impl": self.knowledge_impl,
            "model_confidence_impl": self.model_confidence_impl,
            "environment_impl": self.environment_impl,
            "environment_scope": self.environment_scope,
            "activation_policy_id": policy_id,
            "created_from_commit": self.created_from_commit,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError(f"Missing protocol fields: {missing}")
        if not self.assignments:
            raise ValueError("At least one group assignment is required")
        self.validate_disjointness()
        expected = self.compute_protocol_id()
        if self.protocol_id and self.protocol_id != expected:
            raise ValueError("Development protocol hash mismatch")

    def semantic_activation_policy_id(self) -> str:
        current = str(self.activation_policy_id or "").strip()
        legacy = str(self.activation_policy_sha256 or "").strip()
        if current and legacy and current != legacy:
            raise ValueError("Conflicting activation policy IDs in protocol")
        return current or legacy

    def validate_disjointness(self) -> None:
        by_group: dict[str, str] = {}
        task_seed_pairs: dict[tuple[str, str], str] = {}
        for assignment in self.assignments:
            previous = by_group.setdefault(assignment.group_id, assignment.role)
            if previous != assignment.role:
                raise ValueError(
                    f"group {assignment.group_id!r} crosses {previous} and "
                    f"{assignment.role}"
                )
            key = (assignment.task, assignment.seed)
            previous_pair = task_seed_pairs.setdefault(key, assignment.role)
            if previous_pair != assignment.role:
                raise ValueError(
                    f"task-seed pair {key!r} crosses {previous_pair} and "
                    f"{assignment.role}"
                )
        roles = {item.role for item in self.assignments}
        missing_roles = DEVELOPMENT_ROLES - roles
        if missing_roles:
            raise ValueError(f"Protocol is missing roles: {sorted(missing_roles)}")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("protocol_id", None)
        payload.pop("activation_policy_sha256", None)
        payload["schema_version"] = PROTOCOL_SCHEMA_VERSION
        payload["activation_policy_id"] = self.semantic_activation_policy_id()
        payload["assignments"] = [
            item.to_dict()
            for item in sorted(
                self.assignments,
                key=lambda item: (
                    item.role,
                    item.task,
                    item.seed,
                    item.group_id,
                ),
            )
        ]
        payload["environment_parameters"] = dict(
            sorted(self.environment_parameters.items())
        )
        return payload

    def compute_protocol_id(self) -> str:
        return hashlib.sha256(_canonical_json(self.payload_without_id())).hexdigest()

    def with_id(self) -> "DevelopmentProtocolManifest":
        return replace(self, protocol_id=self.compute_protocol_id())

    def to_dict(self) -> dict[str, Any]:
        manifest = self if self.protocol_id else self.with_id()
        payload = manifest.payload_without_id()
        payload["protocol_id"] = manifest.protocol_id
        return payload

    def groups_for(self, role: str) -> frozenset[str]:
        if role not in DEVELOPMENT_ROLES:
            raise ValueError(f"Unknown development role {role!r}")
        return frozenset(
            item.group_id for item in self.assignments if item.role == role
        )

    def assignment_map(self) -> dict[str, GroupAssignment]:
        return {item.group_id: item for item in self.assignments}


def save_protocol(path: str | Path, manifest: DevelopmentProtocolManifest) -> str:
    manifest = manifest.with_id()
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    return manifest.protocol_id


def load_protocol(path: str | Path) -> DevelopmentProtocolManifest:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    payload["assignments"] = tuple(
        GroupAssignment(**item) for item in payload["assignments"]
    )
    if "activation_policy_id" not in payload and "activation_policy_sha256" in payload:
        payload["activation_policy_id"] = payload["activation_policy_sha256"]
    payload["schema_version"] = PROTOCOL_SCHEMA_VERSION
    payload.pop("activation_policy_sha256", None)
    return DevelopmentProtocolManifest(**payload)
