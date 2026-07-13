#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests_dc3pa.helpers_stage6_cobblestone import (  # noqa: E402
    ACCEPT_CONFLICT_SCENARIO,
    GOAL_FALSE_SCENARIO,
    HAPPY_PATH_SCENARIO,
    run_controlled_cobblestone_script,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the controlled Stage 6 cobblestone closed-loop validation"
    )
    parser.add_argument(
        "--scenario",
        choices=(
            HAPPY_PATH_SCENARIO,
            ACCEPT_CONFLICT_SCENARIO,
            GOAL_FALSE_SCENARIO,
        ),
        default=HAPPY_PATH_SCENARIO,
    )
    parser.add_argument("--temp-root", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = run_controlled_cobblestone_script(
        scenario=args.scenario,
        temp_root=args.temp_root,
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
