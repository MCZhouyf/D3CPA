#!/usr/bin/env python3
"""Freeze directed features and the Round 5.12.4 pre-fit qualification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round5124_fusion_data import (
    freeze_feature_direction,
    qualify_pre_fusion,
    write_json_immutable,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    for name in (
        "raw-fusion-release",
        "raw-train",
        "raw-tune",
        "standard-acceptance",
        "standard-closeout",
        "confidence-release",
        "environment-release",
        "l2-provenance",
        "bootstrap-policy",
        "transformed-train",
        "transformed-tune",
        "feature-direction-policy-output",
        "qualification-output",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    direction, train, tune = freeze_feature_direction(
        source_commit=args.source_commit,
        raw_fusion_release_path=args.raw_fusion_release,
        raw_train_path=args.raw_train,
        raw_tune_path=args.raw_tune,
        transformed_train_path=args.transformed_train,
        transformed_tune_path=args.transformed_tune,
    )
    qualification = qualify_pre_fusion(
        source_commit=args.source_commit,
        standard_acceptance_path=args.standard_acceptance,
        standard_closeout_path=args.standard_closeout,
        confidence_release_path=args.confidence_release,
        environment_release_path=args.environment_release,
        fusion_feature_release_path=args.raw_fusion_release,
        feature_direction_policy=direction,
        l2_provenance_path=args.l2_provenance,
        bootstrap_policy_path=args.bootstrap_policy,
        train_records=train,
        tune_records=tune,
    )
    write_json_immutable(
        args.feature_direction_policy_output,
        direction.to_dict(),
    )
    write_json_immutable(args.qualification_output, qualification.to_dict())
    print(
        json.dumps(
            {
                "feature_direction_policy_id": direction.policy_id,
                "pre_fusion_qualification_id": qualification.report_id,
                "eligible": qualification.eligible,
                "train_rows": len(train),
                "tune_rows": len(tune),
                "holdout_opened": False,
                "fusion_fitted": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
