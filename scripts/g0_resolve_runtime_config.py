#!/usr/bin/env python3
"""Write a credential-free record of the G0 runtime configuration."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/g0_runtime.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config_path = args.config.resolve()
    payload = _mapping(json.loads(config_path.read_text(encoding="utf-8")), "config")
    model = _mapping(payload.get("model"), "model")
    budgets = _mapping(payload.get("budgets"), "budgets")
    result = {
        "source_config": str(config_path),
        "resolution_precedence": payload.get("resolution_precedence", []),
        "final": {
            "episode_seed": payload.get("episode_seed"),
            "world_seed": payload.get("episode_seed"),
            "simulator_seed": payload.get("episode_seed"),
            "python_random_seed": payload.get("episode_seed"),
            "numpy_seed": payload.get("episode_seed"),
            "model": model.get("model"),
            "base_url": model.get("base_url"),
            "temperature": model.get("temperature"),
            "top_p": model.get("top_p"),
            "max_tokens": model.get("max_tokens"),
            "max_retries": model.get("max_retries"),
            "credential_source": model.get("api_key_environment_variable"),
            "max_replans_per_task": budgets.get("max_replans_per_task"),
            "max_environment_steps": budgets.get("max_environment_steps"),
            "action_attempts": budgets.get("action_attempts"),
            "feature_flags": payload.get("feature_flags"),
        },
        "secrets_recorded": False,
        "seed_derivation": "world_seed = simulator_seed = EPISODE_SEED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"episode_seed": result["final"]["episode_seed"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
