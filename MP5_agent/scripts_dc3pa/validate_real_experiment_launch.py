#!/usr/bin/env python3
"""Validate a single real-experiment launch request before starting Minecraft."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.binding import load_binding
from dc3pa.experiments.blueprint import load_blueprint
from dc3pa.experiments.launcher_validation import validate_real_experiment_launch
from dc3pa.experiments.phase_state import load_state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blueprint", required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--max-execution-attempts", type=int)
    parser.add_argument("--binding")
    parser.add_argument("--phase-state")
    parser.add_argument("--run-manifest-id", action="append", default=[])
    args = parser.parse_args()

    manifest_ids: dict[str, str] = {}
    for value in args.run_manifest_id:
        if "=" not in value:
            raise SystemExit("--run-manifest-id must use KEY=VALUE")
        key, item = value.split("=", 1)
        if not key.strip() or not item.strip():
            raise SystemExit("--run-manifest-id key/value cannot be empty")
        manifest_ids[key.strip()] = item.strip()

    result = validate_real_experiment_launch(
        blueprint=load_blueprint(args.blueprint),
        binding=load_binding(args.binding) if args.binding else None,
        phase_state=load_state(args.phase_state) if args.phase_state else None,
        phase=args.phase,
        task=args.task,
        seed=args.seed,
        max_execution_attempts=args.max_execution_attempts,
        run_manifest_ids=manifest_ids,
    )
    print(json.dumps(result.to_trace_payload(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
