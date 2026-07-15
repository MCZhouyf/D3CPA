"""Capture immutable machine-readable evidence for a subprocess command."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = 1
_PASSED_PATTERN = re.compile(r"(?<!\d)(\d+)\s+passed\b")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True)
class CommandEvidenceReport:
    evidence_name: str
    source_commit: str
    command: tuple[str, ...]
    working_directory_fingerprint: str
    started_at: str
    finished_at: str
    exit_code: int
    stdout_sha256: str
    stderr_sha256: str
    stdout_size_bytes: int
    stderr_size_bytes: int
    parsed_passed_count: int
    passed: bool
    environment_keys_recorded: tuple[str, ...] = ()
    schema_version: int = SCHEMA_VERSION
    evidence_id: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("Unsupported command evidence schema")
        if not self.evidence_name or not self.source_commit or not self.command:
            raise ValueError("Command evidence identity is incomplete")
        expected = self.compute_evidence_id()
        if self.evidence_id and self.evidence_id != expected:
            raise ValueError("Command evidence hash mismatch")

    def payload_without_id(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("evidence_id", None)
        payload["command"] = list(self.command)
        payload["environment_keys_recorded"] = list(
            self.environment_keys_recorded
        )
        return payload

    def compute_evidence_id(self) -> str:
        return hashlib.sha256(
            _canonical_json(self.payload_without_id())
        ).hexdigest()

    def with_id(self) -> "CommandEvidenceReport":
        return replace(self, evidence_id=self.compute_evidence_id())

    def to_dict(self) -> dict[str, Any]:
        item = self if self.evidence_id else self.with_id()
        payload = item.payload_without_id()
        payload["evidence_id"] = item.evidence_id
        return payload


def run_command_evidence(
    *,
    evidence_name: str,
    source_commit: str,
    command: Sequence[str],
    cwd: str | Path,
    output_root: str | Path,
    safe_environment_keys: Sequence[str] = (),
) -> CommandEvidenceReport:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    stdout_path = root / "stdout.txt"
    stderr_path = root / "stderr.txt"
    report_path = root / "evidence.json"
    if any(path.exists() for path in (stdout_path, stderr_path, report_path)):
        raise FileExistsError("Command evidence output files already exist")

    started = utc_now()
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        result = subprocess.run(
            list(command),
            cwd=Path(cwd),
            stdout=stdout,
            stderr=stderr,
            check=False,
        )
    finished = utc_now()

    stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
    counts = [
        int(match)
        for match in _PASSED_PATTERN.findall(stdout_text + "\n" + stderr_text)
    ]
    passed_count = max(counts, default=0)
    report = CommandEvidenceReport(
        evidence_name=evidence_name,
        source_commit=source_commit,
        command=tuple(str(item) for item in command),
        working_directory_fingerprint=hashlib.sha256(
            str(Path(cwd).resolve()).encode("utf-8")
        ).hexdigest(),
        started_at=started,
        finished_at=finished,
        exit_code=int(result.returncode),
        stdout_sha256=sha256_file(stdout_path),
        stderr_sha256=sha256_file(stderr_path),
        stdout_size_bytes=stdout_path.stat().st_size,
        stderr_size_bytes=stderr_path.stat().st_size,
        parsed_passed_count=passed_count,
        passed=result.returncode == 0,
        environment_keys_recorded=tuple(sorted(safe_environment_keys)),
    ).with_id()
    report_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
