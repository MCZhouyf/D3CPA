#!/usr/bin/env python3
"""Fit a strict ordinal calibration artifact from Round-3 calibration episodes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.reliability.confidence_observation import ModelConfidenceObservation
from dc3pa.reliability.ordinal_calibration import fit_ordinal_calibration
from dc3pa.reliability.ordinal_confidence import ordinal_prompt_template_sha256
from dc3pa.reliability.step_labels import join_confidence_with_execution
from dc3pa.experiments.dry_run import ensure_not_dry_run_artifact_path


def _episode_payloads(root: Path) -> Iterable[Mapping[str, Any]]:
    episodes_dir = root / "episodes"
    if not episodes_dir.exists():
        raise FileNotFoundError(f"calibration episodes directory not found: {episodes_dir}")
    for path in sorted(episodes_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        record = payload.get("record", payload)
        if not isinstance(record, Mapping):
            raise ValueError(f"invalid calibration record: {path}")
        yield record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibration-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--prompt-version", default="ordinal-v1")
    parser.add_argument("--created-from-commit", required=True)
    parser.add_argument("--alpha", type=float, default=1.0)
    parser.add_argument("--min-total-samples", type=int, default=50)
    parser.add_argument("--min-observed-levels", type=int, default=3)
    parser.add_argument("--examples-output", type=Path)
    parser.add_argument("--diagnostics-output", type=Path)
    args = parser.parse_args()

    ensure_not_dry_run_artifact_path(
        args.calibration_root,
        label="calibration root",
    )
    examples = []
    excluded = []
    for record in _episode_payloads(args.calibration_root):
        observations_raw = record.get("confidence_observations")
        if observations_raw is None:
            observations_raw = dict(record.get("metadata", {})).get(
                "model_confidence_observations", []
            )
        observations = [
            ModelConfidenceObservation.from_mapping(item) for item in observations_raw or []
        ]
        joined, dropped = join_confidence_with_execution(
            episode_id=str(record.get("episode_id", "")),
            plan=dict(record.get("plan", {})),
            telemetry=tuple(record.get("telemetry", ())),
            observations=observations,
        )
        examples.extend(joined)
        excluded.extend(dropped)

    samples = [item.to_ordinal_sample() for item in examples]
    artifact = fit_ordinal_calibration(
        samples,
        model_id=args.model_id,
        prompt_version=args.prompt_version,
        prompt_sha256=ordinal_prompt_template_sha256(),
        created_from_commit=args.created_from_commit,
        alpha=args.alpha,
        min_total_samples=args.min_total_samples,
        min_observed_levels=args.min_observed_levels,
        metadata={
            "calibration_root": str(args.calibration_root.resolve()),
            "included_examples": len(examples),
            "excluded_examples": len(excluded),
        },
    )
    artifact.save(args.output)

    if args.examples_output:
        args.examples_output.parent.mkdir(parents=True, exist_ok=True)
        args.examples_output.write_text(
            "\n".join(json.dumps(item.to_dict(), sort_keys=True) for item in examples)
            + ("\n" if examples else ""),
            encoding="utf-8",
        )
    diagnostics = {
        "included": len(examples),
        "excluded": len(excluded),
        "exclusion_reasons": {},
        "artifact_id": artifact.artifact_id,
        "metrics": artifact.metrics,
        "sample_counts": artifact.sample_counts,
    }
    for item in excluded:
        diagnostics["exclusion_reasons"][item.reason] = (
            diagnostics["exclusion_reasons"].get(item.reason, 0) + 1
        )
    if args.diagnostics_output:
        args.diagnostics_output.parent.mkdir(parents=True, exist_ok=True)
        args.diagnostics_output.write_text(
            json.dumps(diagnostics, indent=2, sort_keys=True), encoding="utf-8"
        )
    print(json.dumps(diagnostics, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
