#!/usr/bin/env python3
"""Freeze Round 5.12.4 fit and activation policies before fitting."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round5124_fusion_fit import (
    freeze_fit_policies,
    write_json_immutable,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    for name in (
        "qualification",
        "feature-direction",
        "l2-provenance",
        "bootstrap-policy",
        "fit-policy-output",
        "activation-policy-output",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    fit, activation = freeze_fit_policies(
        source_commit=args.source_commit,
        qualification_path=args.qualification,
        feature_direction_path=args.feature_direction,
        l2_provenance_path=args.l2_provenance,
        bootstrap_policy_path=args.bootstrap_policy,
    )
    write_json_immutable(args.fit_policy_output, fit.to_dict())
    write_json_immutable(args.activation_policy_output, activation.to_dict())
    print(
        json.dumps(
            {
                "fit_policy_id": fit.policy_id,
                "activation_policy_id": activation.policy_id,
                "l2_candidate_values": list(fit.l2_candidate_values),
                "primary_bootstrap_unit": activation.primary_bootstrap_unit,
                "holdout_opened": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
