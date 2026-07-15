#!/usr/bin/env python3
"""Validate a DC3PA real-experiment pack and write its current runbook."""

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
from dc3pa.experiments.pack import render_runbook, validate_pack
from dc3pa.experiments.phase_state import load_state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blueprint", required=True)
    parser.add_argument("--activation-policy", required=True)
    parser.add_argument("--data-sufficiency-policy", required=True)
    parser.add_argument("--binding")
    parser.add_argument("--phase-state")
    parser.add_argument("--output-report", required=True)
    parser.add_argument("--output-runbook", required=True)
    args = parser.parse_args()

    report = validate_pack(
        blueprint_path=args.blueprint,
        activation_policy_path=args.activation_policy,
        data_sufficiency_policy_path=args.data_sufficiency_policy,
        binding_path=args.binding,
        state_path=args.phase_state,
    )
    report.require_eligible()
    blueprint = load_blueprint(args.blueprint)
    binding = load_binding(args.binding) if args.binding else None
    state = load_state(args.phase_state) if args.phase_state else None

    Path(args.output_report).write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    Path(args.output_runbook).write_text(
        render_runbook(blueprint=blueprint, binding=binding, state=state),
        encoding="utf-8",
    )
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
