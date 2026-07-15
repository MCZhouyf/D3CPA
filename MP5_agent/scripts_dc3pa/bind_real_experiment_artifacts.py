#!/usr/bin/env python3
"""Bind frozen memory, confidence, and Environment settings to a blueprint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.binding import (
    build_artifact_binding,
    build_bound_development_protocol,
    save_binding,
)
from dc3pa.experiments.blueprint import load_blueprint, sha256_file
from dc3pa.reliability.development_protocol import save_protocol


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blueprint", required=True)
    parser.add_argument("--memory-snapshot-sha256", required=True)
    parser.add_argument("--memory-snapshot-manifest-id", required=True)
    parser.add_argument("--confidence-artifact", required=True)
    parser.add_argument("--confidence-artifact-id", required=True)
    parser.add_argument("--selected-environment-parameters", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output-protocol", required=True)
    parser.add_argument("--output-binding", required=True)
    args = parser.parse_args()

    blueprint = load_blueprint(args.blueprint)
    selected = json.loads(
        Path(args.selected_environment_parameters).read_text(encoding="utf-8")
    )
    protocol = build_bound_development_protocol(
        blueprint=blueprint,
        memory_snapshot_sha256=args.memory_snapshot_sha256,
        confidence_artifact_id=args.confidence_artifact_id,
        selected_environment_parameters=selected,
        protocol_name=f"{blueprint.blueprint_name}-bound-development",
        created_from_commit=args.source_commit,
    )
    save_protocol(args.output_protocol, protocol)
    binding = build_artifact_binding(
        blueprint=blueprint,
        memory_snapshot_sha256=args.memory_snapshot_sha256,
        memory_snapshot_manifest_id=args.memory_snapshot_manifest_id,
        confidence_artifact_id=args.confidence_artifact_id,
        confidence_artifact_file_sha256=sha256_file(args.confidence_artifact),
        selected_environment_parameters=selected,
        source_commit=args.source_commit,
        development_protocol_id=protocol.protocol_id,
    )
    save_binding(args.output_binding, binding)
    print(
        json.dumps(
            {
                "blueprint_id": blueprint.blueprint_id,
                "development_protocol_id": protocol.protocol_id,
                "binding_id": binding.binding_id,
                "environment_parameters": selected,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
