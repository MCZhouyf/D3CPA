#!/usr/bin/env python3
"""Advance the real-experiment phase ledger by exactly one permitted phase."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.phase_state import (
    ExperimentPhaseState,
    load_state,
    save_state_atomic,
)


def parse_artifact(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("artifact must be KEY=VALUE")
    key, item = value.split("=", 1)
    if not key.strip() or not item.strip():
        raise argparse.ArgumentTypeError("artifact key/value cannot be empty")
    return key.strip(), item.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--artifact", action="append", default=[], type=parse_artifact)
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    state_path = Path(args.state)
    if state_path.exists():
        state = load_state(state_path)
        if state.experiment_id != args.experiment_id:
            raise ValueError("Experiment ID does not match existing state")
    else:
        state = ExperimentPhaseState(
            experiment_id=args.experiment_id,
            records=(),
        ).with_id()

    advanced = state.advance(
        phase=args.phase,
        source_commit=args.source_commit,
        artifact_ids=dict(args.artifact),
        notes=args.notes,
    )
    save_state_atomic(state_path, advanced)
    print(json.dumps(advanced.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
