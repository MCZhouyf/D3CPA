#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.round5124_holdout_features import export_holdout_features


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in (
        "decisions",
        "confidence-release",
        "environment-release",
        "candidate",
        "runtime-release",
        "output",
    ):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    summary = export_holdout_features(
        decisions_path=args.decisions,
        confidence_release_path=args.confidence_release,
        environment_release_path=args.environment_release,
        candidate_path=args.candidate,
        runtime_release_path=args.runtime_release,
        output_path=args.output,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
