#!/usr/bin/env python3
"""Check the no-model deterministic portion of the G0 episode-seed contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

import numpy as np


def _run(seed: int) -> dict[str, object]:
    random.seed(seed)
    np.random.seed(seed % (2 ** 32))
    observations = [
        hashlib.sha256(np.random.bytes(32)).hexdigest()
        for _ in range(50)
    ]
    planner_input = {
        "seed": seed,
        "inventory": {"log": random.randint(0, 3)},
        "position": [int(np.random.randint(-5, 6)) for _ in range(3)],
    }
    action_sequence = [
        {"action": "find", "direction": random.randrange(8)}
        for _ in range(20)
    ]
    return {
        "resolved_seed": seed,
        "initial_observation_hash": observations[0],
        "first_50_observation_hashes": observations,
        "planner_input_hash": hashlib.sha256(
            json.dumps(planner_input, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "action_sequence": action_sequence,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    first, second = _run(args.seed), _run(args.seed)
    payload = {
        "seed": args.seed,
        "fixture": "fixed local deterministic fixture; no model or Minecraft process invoked",
        "first": first,
        "second": second,
        "identical": first == second,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"identical": payload["identical"]}, sort_keys=True))
    return 0 if payload["identical"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
