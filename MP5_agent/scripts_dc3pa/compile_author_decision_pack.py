#!/usr/bin/env python3
"""Compile author-supplied decision files into pre-approval Round 5.6 inputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.author_decisions import compile_author_decision_pack


def parse_prompt(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--prompt must use NAME=PATH")
    name, path = value.split("=", 1)
    if not name.strip() or not path.strip():
        raise argparse.ArgumentTypeError("Prompt name/path cannot be empty")
    return name.strip(), path.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--final-tasks", required=True)
    parser.add_argument("--final-seeds", required=True)
    parser.add_argument("--acquisition", required=True)
    parser.add_argument("--development", required=True)
    parser.add_argument("--phase-budgets", required=True)
    parser.add_argument("--settings", required=True)
    parser.add_argument("--activation-policy", required=True)
    parser.add_argument("--data-sufficiency-policy", required=True)
    parser.add_argument("--prompt", action="append", type=parse_prompt, default=[])
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    manifest = compile_author_decision_pack(
        final_tasks_csv=args.final_tasks,
        final_seeds_csv=args.final_seeds,
        acquisition_csv=args.acquisition,
        development_csv=args.development,
        budgets_csv=args.phase_budgets,
        settings_json=args.settings,
        activation_policy_json=args.activation_policy,
        data_sufficiency_policy_json=args.data_sufficiency_policy,
        prompt_files=dict(args.prompt),
        output_dir=args.output_dir,
    )
    print(json.dumps(manifest.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
