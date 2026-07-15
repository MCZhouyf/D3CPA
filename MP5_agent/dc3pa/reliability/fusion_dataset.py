"""Grouped, leakage-resistant data records for reliability fusion."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from .fusion_features import (
    FEATURE_SCHEMA_VERSION,
    FUSION_FEATURE_NAMES,
    ReliabilityFeatureVector,
)


DATASET_SCHEMA_VERSION = "dc3pa-fusion-dataset-v1"


def _canonical_json(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True)
class FusionExample:
    episode_id: str
    task: str
    seed: str
    plan_id: str
    plan_version: int
    step_id: str
    step_index: int
    group_id: str
    split: str
    label: int
    features: Mapping[str, float]
    hard_conflict: bool = False
    legacy_probability: Optional[float] = None
    confidence_artifact_id: str = ""
    memory_snapshot_sha256: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.label not in (0, 1):
            raise ValueError("label must be 0 or 1")
        if self.split not in {"train", "validation", "test"}:
            raise ValueError("split must be train, validation, or test")
        if set(self.features) != set(FUSION_FEATURE_NAMES):
            raise ValueError(
                f"features must contain exactly {FUSION_FEATURE_NAMES}"
            )
        for name in FUSION_FEATURE_NAMES:
            value = float(self.features[name])
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.legacy_probability is not None:
            value = float(self.legacy_probability)
            if not 0.0 <= value <= 1.0:
                raise ValueError("legacy_probability must be in [0, 1]")
        if not self.group_id:
            raise ValueError("group_id is required to prevent leakage")

    @property
    def stable_key(self) -> tuple[str, int, str]:
        return (self.plan_id, self.plan_version, self.step_id)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["features"] = dict(self.features)
        payload["metadata"] = dict(self.metadata)
        payload["dataset_schema_version"] = DATASET_SCHEMA_VERSION
        payload["feature_schema_version"] = FEATURE_SCHEMA_VERSION
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "FusionExample":
        data = dict(payload)
        data.pop("dataset_schema_version", None)
        data.pop("feature_schema_version", None)
        return cls(**data)


@dataclass(frozen=True)
class PendingFusionObservation:
    episode_id: str
    task: str
    seed: str
    plan_id: str
    plan_version: int
    step_id: str
    step_index: int
    group_id: str
    split: str
    vector: ReliabilityFeatureVector
    legacy_probability: Optional[float] = None
    memory_snapshot_sha256: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def stable_key(self) -> tuple[str, int, str]:
        return (self.plan_id, self.plan_version, self.step_id)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["vector"] = self.vector.to_dict()
        payload["metadata"] = dict(self.metadata)
        return payload


class FusionObservationStore:
    """Append-only JSONL store for pre-execution fusion observations.

    This is intentionally separate from long-term memory. It records development
    evidence used for offline fusion fitting and never writes to frozen memory.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, observation: PendingFusionObservation) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    observation.to_dict(),
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )


def join_observations_and_labels(
    observations: Sequence[PendingFusionObservation],
    labels: Mapping[tuple[str, int, str], Optional[int]],
) -> tuple[list[FusionExample], list[dict[str, Any]]]:
    """Join pre-execution features with execution labels by plan version and step ID.

    Censored, deleted, or ambiguous steps must enter ``labels`` as ``None`` and
    are excluded rather than being converted into failures.
    """

    examples: list[FusionExample] = []
    exclusions: list[dict[str, Any]] = []
    for item in observations:
        if not item.vector.available:
            exclusions.append(
                {
                    "key": item.stable_key,
                    "reason": item.vector.exclusion_reason or "feature unavailable",
                }
            )
            continue
        label = labels.get(item.stable_key)
        if label not in (0, 1):
            exclusions.append(
                {
                    "key": item.stable_key,
                    "reason": "missing, censored, or ambiguous execution label",
                }
            )
            continue
        examples.append(
            FusionExample(
                episode_id=item.episode_id,
                task=item.task,
                seed=item.seed,
                plan_id=item.plan_id,
                plan_version=item.plan_version,
                step_id=item.step_id,
                step_index=item.step_index,
                group_id=item.group_id,
                split=item.split,
                label=int(label),
                features=item.vector.as_feature_dict(),
                hard_conflict=item.vector.hard_conflict,
                legacy_probability=item.legacy_probability,
                confidence_artifact_id=item.vector.confidence_artifact_id,
                memory_snapshot_sha256=item.memory_snapshot_sha256,
                metadata=dict(item.metadata),
            )
        )
    examples.sort(
        key=lambda item: (
            item.split,
            item.group_id,
            item.plan_id,
            item.plan_version,
            item.step_index,
            item.step_id,
        )
    )
    return examples, exclusions


def validate_group_isolation(examples: Sequence[FusionExample]) -> None:
    seen: dict[str, str] = {}
    for item in examples:
        previous = seen.setdefault(item.group_id, item.split)
        if previous != item.split:
            raise ValueError(
                f"group {item.group_id!r} appears in both {previous} and {item.split}"
            )


def dataset_sha256(examples: Sequence[FusionExample]) -> str:
    validate_group_isolation(examples)
    payload = [item.to_dict() for item in sorted(
        examples,
        key=lambda item: (
            item.split,
            item.group_id,
            item.plan_id,
            item.plan_version,
            item.step_index,
            item.step_id,
        ),
    )]
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def save_jsonl(path: Path, examples: Sequence[FusionExample]) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    validate_group_isolation(examples)
    ordered = sorted(
        examples,
        key=lambda item: (
            item.split,
            item.group_id,
            item.plan_id,
            item.plan_version,
            item.step_index,
            item.step_id,
        ),
    )
    with path.open("w", encoding="utf-8") as handle:
        for item in ordered:
            handle.write(
                json.dumps(
                    item.to_dict(),
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )
    return dataset_sha256(ordered)


def load_jsonl(path: Path) -> list[FusionExample]:
    items: list[FusionExample] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                items.append(FusionExample.from_dict(payload))
            except Exception as exc:
                raise ValueError(f"Invalid dataset line {line_number}: {exc}") from exc
    validate_group_isolation(items)
    return items
