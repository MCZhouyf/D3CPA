#!/usr/bin/env python3
"""Build a tiny, permanently excluded dry-run campaign from dev_train groups."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dc3pa.experiments.blueprint import load_blueprint
from dc3pa.experiments.dry_run import build_dry_run_campaign, save_campaign
from dc3pa.experiments.phase_state import load_state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blueprint", required=True)
    parser.add_argument("--group-id", action="append", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--phase-state")
    parser.add_argument("--output-campaign", required=True)
    parser.add_argument(
        "--allow-no-confidence-observations",
        action="store_true",
    )
    parser.add_argument(
        "--allow-no-label-joins",
        action="store_true",
    )
    args = parser.parse_args()

    campaign = build_dry_run_campaign(
        blueprint=load_blueprint(args.blueprint),
        selected_group_ids=args.group_id,
        source_commit=args.source_commit,
        phase_state=load_state(args.phase_state) if args.phase_state else None,
        require_confidence_observations=not args.allow_no_confidence_observations,
        require_execution_label_joins=not args.allow_no_label_joins,
    )
    save_campaign(args.output_campaign, campaign)
    print(json.dumps(campaign.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
