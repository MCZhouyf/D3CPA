#!/usr/bin/env python3
"""Plan one fixed ten-entry formal-acquisition health batch."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.formal_acquisition_batch import plan_batch
from dc3pa.experiments.formal_acquisition_execution import (
    FormalAcquisitionCampaign,
    TechnicalRetryPolicy,
    load_ledger,
)


def load(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--schedule", required=True)
    parser.add_argument("--ledger-root", required=True)
    parser.add_argument("--retry-policy", required=True)
    parser.add_argument("--batch-index", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    campaign = FormalAcquisitionCampaign(**load(args.campaign))
    retry_payload = load(args.retry_policy)
    retry_payload["allowed_categories"] = tuple(
        retry_payload["allowed_categories"]
    )
    retry_payload["scientific_categories"] = tuple(
        retry_payload["scientific_categories"]
    )
    retry = TechnicalRetryPolicy(**retry_payload)
    ledgers = [
        load_ledger(path)
        for path in sorted(Path(args.ledger_root).glob("*.json"))
    ]
    result = plan_batch(
        campaign=campaign,
        schedule=load(args.schedule),
        ledgers=ledgers,
        retry_policy=retry,
        batch_index=args.batch_index,
    )
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
