#!/usr/bin/env python3
"""Freeze Round 5.13E0 forensic artifacts without mutating frozen inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.readonly_snapshot_smoke import run_readonly_snapshot_smoke
from dc3pa.experiments.round513e_provenance import (
    audit_mineclip_identity,
    build_blocked_v2_audit,
    build_scene_exemplar_evidence_release,
)


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_exclusive(path: Path, payload: object) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, sort_keys=True, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--blocked-v1-audit", type=Path, required=True)
    parser.add_argument("--referenced-policy-id", required=True)
    parser.add_argument("--referenced-policy-payload", type=Path)
    parser.add_argument("--referenced-policy-match-count", type=int, required=True)
    parser.add_argument("--missing-scene-release-id", required=True)
    parser.add_argument("--historical-scene-release-match-count", type=int, required=True)
    parser.add_argument("--actual-policy", type=Path, required=True)
    parser.add_argument("--checkpoint-manifest", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--snapshot-manifest", type=Path, required=True)
    parser.add_argument("--acquisition-manifest", type=Path, required=True)
    parser.add_argument("--lineage-input", type=Path, required=True)
    parser.add_argument("--lineage-audit", type=Path, required=True)
    parser.add_argument("--paper-memory-release", type=Path, required=True)
    parser.add_argument("--frozen-memory-release", type=Path, required=True)
    parser.add_argument("--quarantined-prior-scene-release-id")
    args = parser.parse_args()

    source = subprocess.check_output(
        ("git", "rev-parse", "HEAD"), cwd=ROOT.parent, text=True
    ).strip()
    if source != args.expected_source_commit:
        raise ValueError("Round 5.13E0 source commit mismatch")
    if subprocess.check_output(
        ("git", "status", "--short"), cwd=ROOT.parent, text=True
    ).strip():
        raise ValueError("Round 5.13E0 freezing requires a clean worktree")

    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Round 5.13E0 output root must be empty")

    v1_before = _sha(args.blocked_v1_audit)
    blocked_v1 = _load(args.blocked_v1_audit)
    mineclip = audit_mineclip_identity(
        source_commit=source,
        referenced_policy_id=args.referenced_policy_id,
        actual_policy_path=args.actual_policy,
        checkpoint_manifest_path=args.checkpoint_manifest,
        checkpoint_path=args.checkpoint,
        referenced_policy_path=args.referenced_policy_payload,
        searched_exact_id_match_count=args.referenced_policy_match_count,
        referenced_source_label=(
            "resolved-immutable-policy" if args.referenced_policy_payload else None
        ),
    )
    scene_audit, scene_release = build_scene_exemplar_evidence_release(
        source_commit=source,
        missing_historical_release_id=args.missing_scene_release_id,
        exact_historical_release_match_count=args.historical_scene_release_match_count,
        snapshot_manifest_path=args.snapshot_manifest,
        acquisition_manifest_path=args.acquisition_manifest,
        lineage_input_path=args.lineage_input,
        lineage_audit_path=args.lineage_audit,
        paper_memory_release_path=args.paper_memory_release,
        frozen_memory_release_path=args.frozen_memory_release,
        mineclip_checkpoint_manifest_path=args.checkpoint_manifest,
    )
    snapshot_smoke = run_readonly_snapshot_smoke(args.snapshot_manifest)
    v1_after = _sha(args.blocked_v1_audit)
    v2 = build_blocked_v2_audit(
        source_commit=source,
        blocked_v1_audit_id=str(blocked_v1["audit_id"]),
        blocked_v1_audit_sha256_before=v1_before,
        blocked_v1_audit_sha256_after=v1_after,
        mineclip_audit=mineclip,
        scene_audit=scene_audit,
        scene_release=scene_release,
        snapshot_guard_passed=snapshot_smoke.eligible,
    )

    artifacts = [
        ("mineclip_identity_forensic_audit.json", mineclip.to_dict(), mineclip.audit_id),
        ("scene_exemplar_release_forensic_audit.json", scene_audit.to_dict(), scene_audit.audit_id),
        ("round513e_presmoke_integrity_audit_v2.json", v2.to_dict(), v2.audit_id),
        ("readonly_snapshot_smoke.json", snapshot_smoke.to_dict(), snapshot_smoke.smoke_id),
    ]
    if scene_release is not None:
        artifacts.append(
            (
                "scene_exemplar_evidence_release_v5.json",
                scene_release.to_dict(),
                scene_release.release_id,
            )
        )
    entries = []
    for filename, payload, object_id in artifacts:
        path = output / filename
        _write_exclusive(path, payload)
        entries.append(
            {"filename": filename, "id": object_id, "sha256": _sha(path)}
        )
    manifest = {
        "schema_version": 1,
        "source_commit": source,
        "mineclip_case": mineclip.case,
        "scene_case": scene_audit.case,
        "presmoke_v2_status": v2.status,
        "contract_supersession_created": False,
        "smoke_preparation_created": False,
        "minedojo_started": False,
        "quarantined_prior_scene_release_ids": (
            [args.quarantined_prior_scene_release_id]
            if args.quarantined_prior_scene_release_id
            else []
        ),
        "artifacts": entries,
    }
    _write_exclusive(output / "manifest.json", manifest)
    print(json.dumps(manifest, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
