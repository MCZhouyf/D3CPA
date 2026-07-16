#!/usr/bin/env python3
"""Build paired natural-readiness and fallback-diagnostic campaign binding."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.paired_dry_run import build_paired_protocol


def load(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol-name", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--blueprint-id", required=True)
    parser.add_argument("--model-profile-id", required=True)
    parser.add_argument("--prompt-hash-bundle-id", required=True)
    parser.add_argument("--natural-campaign", required=True)
    parser.add_argument("--diagnostic-campaign", required=True)
    parser.add_argument("--fallback-policy-id", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    item = build_paired_protocol(
        protocol_name=args.protocol_name,
        source_commit=args.source_commit,
        blueprint_id=args.blueprint_id,
        model_profile_id=args.model_profile_id,
        prompt_hash_bundle_id=args.prompt_hash_bundle_id,
        natural_campaign=load(args.natural_campaign),
        diagnostic_campaign=load(args.diagnostic_campaign),
        fallback_policy_id=args.fallback_policy_id,
    )

    output = Path(args.output)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(item.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(item.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
