#!/usr/bin/env python3
"""Freeze the list of pre-fix evidence that must be regenerated."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.controller_revision import (
    EvidenceInvalidationManifest,
    InvalidatedEvidence,
)


REQUIRED_REGENERATION = (
    "github_actions",
    "full_pytest",
    "minedojo_marker",
    "controller_identity",
    "task_semantic_smoke",
    "final_taskset_release",
    "schema_v2_design",
    "semantic_migration",
    "approval_binding",
    "blueprint_validation",
    "model_epoch",
    "six_entry_readiness_campaign",
    "acquisition_readiness",
    "preacquisition_gate",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    artifacts = tuple(
        InvalidatedEvidence(**item) for item in payload["artifacts"]
    )
    item = EvidenceInvalidationManifest(
        manifest_name=payload["manifest_name"],
        previous_source_commit=payload["previous_source_commit"],
        replacement_source_commit=payload["replacement_source_commit"],
        controller_revision_id=payload["controller_revision_id"],
        artifacts=artifacts,
        required_regeneration_labels=tuple(REQUIRED_REGENERATION),
    ).with_id()

    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(item.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(item.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
