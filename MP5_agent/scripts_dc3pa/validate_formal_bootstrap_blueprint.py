#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.blueprint import load_blueprint
from dc3pa.experiments.formal_bootstrap_approval import (
    load_formal_bootstrap_approval,
    validate_formal_bootstrap_blueprint,
)


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blueprint", required=True, type=Path)
    parser.add_argument("--approval-binding", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--amendment", required=True, type=Path)
    parser.add_argument("--controller-source", required=True, type=Path)
    parser.add_argument("--evaluator-source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = validate_formal_bootstrap_blueprint(
        blueprint=load_blueprint(args.blueprint),
        binding=load_formal_bootstrap_approval(args.approval_binding),
        policy=load(args.policy),
        amendment=load(args.amendment),
        controller_source=args.controller_source,
        evaluator_source=args.evaluator_source,
    )
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return 0 if report.eligible else 2


if __name__ == "__main__":
    raise SystemExit(main())
