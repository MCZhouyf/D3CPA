"""Single-use lock and attempt ledger for development holdout evaluation."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional


HOLDOUT_LOCK_SCHEMA_VERSION = 1
LEDGER_SCHEMA_VERSION = 1


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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class HoldoutLockManifest:
    lock_name: str
    holdout_dataset_sha256: str
    development_protocol_id: str
    activation_policy_id: str
    fusion_artifact_id: str
    fusion_artifact_sha256: str
    final_test_exclusion_id: str
    collection_manifest_id: str
    memory_snapshot_sha256: str
    confidence_artifact_id: str
    environment_parameter_sha256: str
    source_commit: str
    created_at: str
    schema_version: int = HOLDOUT_LOCK_SCHEMA_VERSION
    lock_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != HOLDOUT_LOCK_SCHEMA_VERSION:
            raise ValueError("Unsupported holdout lock schema")
        values = asdict(self)
        for key, value in values.items():
            if key not in {"schema_version", "lock_id"} and not str(value).strip():
                raise ValueError(f"Holdout lock field {key} is required")
        expected = self.compute_lock_id()
        if self.lock_id and self.lock_id != expected:
            raise ValueError("Holdout lock hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("lock_id", None)
        return payload

    def compute_lock_id(self) -> str:
        return hashlib.sha256(_canonical_json(self.payload_without_id())).hexdigest()

    def with_id(self) -> "HoldoutLockManifest":
        return replace(self, lock_id=self.compute_lock_id())

    def to_dict(self) -> dict[str, Any]:
        lock = self if self.lock_id else self.with_id()
        payload = lock.payload_without_id()
        payload["lock_id"] = lock.lock_id
        return payload

    def validate_files(
        self,
        *,
        holdout_dataset: str | Path,
        fusion_artifact: str | Path,
    ) -> None:
        if sha256_file(holdout_dataset) != self.holdout_dataset_sha256:
            raise ValueError("Locked holdout dataset hash mismatch")
        if sha256_file(fusion_artifact) != self.fusion_artifact_sha256:
            raise ValueError("Locked fusion artifact file hash mismatch")


@dataclass(frozen=True)
class HoldoutAttemptLedger:
    attempt_id: str
    lock_id: str
    status: str
    started_at: str
    output_report_path: str
    source_commit: str
    finished_at: str = ""
    report_sha256: str = ""
    error_type: str = ""
    error_message: str = ""
    schema_version: int = LEDGER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status not in {"started", "completed", "failed"}:
            raise ValueError("Unknown holdout attempt status")


def save_holdout_lock(
    path: str | Path,
    lock: HoldoutLockManifest,
    *,
    refuse_overwrite: bool = True,
) -> str:
    output = Path(path)
    if output.exists() and refuse_overwrite:
        raise FileExistsError(f"Holdout lock already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = lock.with_id()
    output.write_text(
        json.dumps(lock.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return lock.lock_id


def load_holdout_lock(path: str | Path) -> HoldoutLockManifest:
    return HoldoutLockManifest(
        **json.loads(Path(path).read_text(encoding="utf-8"))
    )


def claim_holdout_attempt(
    ledger_path: str | Path,
    *,
    lock: HoldoutLockManifest,
    output_report_path: str | Path,
    source_commit: str,
) -> HoldoutAttemptLedger:
    path = Path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = HoldoutAttemptLedger(
        attempt_id=str(uuid.uuid4()),
        lock_id=lock.lock_id or lock.compute_lock_id(),
        status="started",
        started_at=utc_now(),
        output_report_path=str(Path(output_report_path)),
        source_commit=source_commit,
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(asdict(ledger), handle, indent=2, sort_keys=True)
            handle.write("\n")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return ledger


def _replace_ledger(
    ledger_path: str | Path,
    *,
    expected_status: str,
    replacement: HoldoutAttemptLedger,
) -> None:
    path = Path(ledger_path)
    current = HoldoutAttemptLedger(
        **json.loads(path.read_text(encoding="utf-8"))
    )
    if current.status != expected_status:
        raise ValueError(
            f"Holdout attempt is {current.status}, expected {expected_status}"
        )
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(asdict(replacement), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def complete_holdout_attempt(
    ledger_path: str | Path,
    *,
    report_path: str | Path,
) -> HoldoutAttemptLedger:
    path = Path(ledger_path)
    current = HoldoutAttemptLedger(
        **json.loads(path.read_text(encoding="utf-8"))
    )
    completed = replace(
        current,
        status="completed",
        finished_at=utc_now(),
        report_sha256=sha256_file(report_path),
    )
    _replace_ledger(
        path,
        expected_status="started",
        replacement=completed,
    )
    return completed


def fail_holdout_attempt(
    ledger_path: str | Path,
    *,
    error: BaseException,
) -> HoldoutAttemptLedger:
    path = Path(ledger_path)
    current = HoldoutAttemptLedger(
        **json.loads(path.read_text(encoding="utf-8"))
    )
    failed = replace(
        current,
        status="failed",
        finished_at=utc_now(),
        error_type=type(error).__name__,
        error_message=str(error),
    )
    _replace_ledger(
        path,
        expected_status="started",
        replacement=failed,
    )
    return failed
