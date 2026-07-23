#!/usr/bin/env python3
"""Freeze an honest BLOCKED readiness result when smoke is not authorized."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from dc3pa.experiments.round513_readiness import build_blocked_readiness


ROOT = Path(__file__).resolve().parents[1]
NAMES = (
    "chrmlite_instrumentation_release_v4_1",
    "chrmlite_engineering_smoke_audit",
    "chrmlite_behavior_equivalence_audit",
    "chrmlite_data_readiness_report",
    "round513cd_readiness_decision",
)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _write(path: Path, payload: object) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--synthetic-test-count", type=int, required=True)
    parser.add_argument("--full-environment-import-test-count", type=int, default=0)
    parser.add_argument("--full-environment-import-passed", action="store_true")
    args = parser.parse_args()
    source = subprocess.run(
        ("git", "rev-parse", "HEAD"), cwd=ROOT.parent, check=True,
        capture_output=True, text=True
    ).stdout.strip()
    if source != args.expected_source_commit:
        raise ValueError("Round 5.13D source commit mismatch")
    if subprocess.run(
        ("git", "status", "--short"), cwd=ROOT.parent, check=True,
        capture_output=True, text=True
    ).stdout.strip():
        raise ValueError("Round 5.13D freezing requires a clean worktree")

    contract_root = args.contract_root.resolve()
    authorization = _load(contract_root / "chrmlite_development_collection_authorization.json")
    smoke_design = _load(contract_root / "chrmlite_engineering_smoke_design.json")
    record_schema = _load(contract_root / "chrmlite_decision_record_schema_v4_1.json")
    if authorization.get("engineering_smoke_approved"):
        raise ValueError("This command is only for the unapproved-smoke blocked state")
    if {authorization.get("source_commit"), smoke_design.get("source_commit"), record_schema.get("source_commit")} != {source}:
        raise ValueError("Round 5.13C contracts do not match the D source commit")

    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Round 5.13D readiness output root must be empty")
    objects = build_blocked_readiness(
        source_commit=source,
        smoke_design_id=str(smoke_design["design_id"]),
        authorization_id=str(authorization["authorization_id"]),
        record_schema_id=str(record_schema["schema_id"]),
        synthetic_test_count=args.synthetic_test_count,
        full_environment_import_test_count=args.full_environment_import_test_count,
        full_environment_import_passed=args.full_environment_import_passed,
    )
    entries = []
    for name, item in zip(NAMES, objects):
        path = output / f"{name}.json"
        payload = item.to_dict()
        _write(path, payload)
        entries.append({
            "name": name,
            "id": payload[getattr(item, "_id_field")],
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    _write(output / "manifest.json", {
        "source_commit": source,
        "readiness_state": "BLOCKED",
        "reason": "engineering_smoke_authorization_missing",
        "objects": entries,
    })
    print(json.dumps({"output_root": str(output), "objects": entries}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
